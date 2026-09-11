"""Simple value-and-earnings proposal service for the V2 workflow.

Web research is performed by ChatGPT Work. This service validates normalized
facts, ranks candidates, compares them with the current portfolio, and creates
proposal-only buy or sell decisions. It has no broker connection.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from agent.compliance import ComplianceEngine
from agent.trading_analysis_service import FilePlanStore
from config import DEFAULT_CONFIG, SystemConfig


class SimpleValueInputError(ValueError):
    pass


def _number(value: Any, name: str, *, minimum: Optional[float] = None) -> float:
    if isinstance(value, bool):
        raise SimpleValueInputError(f"{name} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise SimpleValueInputError(f"{name} must be numeric") from exc
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise SimpleValueInputError(f"{name} must be finite and at least {minimum}")
    return result


def _bounded(value: Any, name: str, low: float, high: float) -> float:
    result = _number(value, name)
    if not low <= result <= high:
        raise SimpleValueInputError(f"{name} must be between {low} and {high}")
    return result


def _parse_time(value: Any, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SimpleValueInputError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SimpleValueInputError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _scale(value: float, low: float, high: float, inverse: bool = False) -> float:
    score = max(0.0, min(100.0, (value - low) / (high - low) * 100.0))
    return 100.0 - score if inverse else score


class SimpleValueService:
    policy_version = "simple-value-v2"

    def __init__(
        self,
        config: Optional[SystemConfig] = None,
        store: Optional[FilePlanStore] = None,
        clock=None,
    ):
        self.config = config or DEFAULT_CONFIG
        self.compliance = ComplianceEngine(self.config.compliance)
        self.store = store or FilePlanStore()
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def get_policy(self) -> Dict[str, Any]:
        return {
            "policy_version": self.policy_version,
            "objective": "Buy a small number of profitable, reasonably valued companies and monitor earnings.",
            "candidate_rules": {
                "eps_ttm": "greater than zero; higher is better but is not comparable across share prices by itself",
                "pe_ttm": "greater than zero and at most 25; lower is better",
                "eps_growth_yoy": "prefer positive growth",
                "evidence": "at least two sources, including one primary earnings release or SEC filing",
            },
            "portfolio_rules": {
                "maximum_new_positions_per_run": 1,
                "maximum_position_weight": .20,
                "minimum_cash_buffer": .10,
                "minimum_purchase": 5.0,
                "maximum_shortlist": 5,
                "no_margin_or_leverage": True,
            },
            "sell_policy": "Propose, never automatically execute. Two ordinary sell signals or one severe signal are required.",
            "restricted_tickers": sorted(self.config.compliance.restricted_tickers),
            "execution_owner": "ChatGPT Work using the separately authenticated Robinhood Trading MCP",
        }

    def get_research_requirements(self) -> Dict[str, Any]:
        return {
            "candidate_fields": [
                "symbol", "company_name", "sector", "price", "eps_ttm", "pe_ttm",
                "eps_growth_yoy", "next_earnings_date", "analyst_target_mean",
                "analyst_consensus", "news_sentiment", "tradable",
                "fractional_tradable", "research_as_of", "evidence",
            ],
            "holding_monitor_fields": [
                "symbol", "price", "eps_ttm", "prior_eps_ttm", "pe_ttm",
                "sector_median_pe", "last_earnings_surprise_pct", "guidance_direction",
                "next_earnings_date", "analyst_target_mean", "analyst_consensus",
                "news_sentiment", "material_negative_news", "research_as_of", "evidence",
            ],
            "source_rules": [
                "Use a primary earnings release or SEC filing for reported EPS and earnings claims.",
                "Use a clearly identified market-data source for price and P/E.",
                "Use reputable published reporting for analyst targets and material news.",
                "Record title, URL, publisher, and observed_at for every source.",
                "Do not present analyst targets or news predictions as facts.",
            ],
        }

    def shortlist(self, candidates: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        ranked: List[Dict[str, Any]] = []
        seen = set()
        now = self.clock().astimezone(timezone.utc)
        for raw in candidates:
            symbol = str(raw.get("symbol", "")).strip().upper()
            if not symbol or symbol in seen:
                raise SimpleValueInputError(f"missing or duplicate symbol: {symbol}")
            seen.add(symbol)
            price = _number(raw.get("price"), f"{symbol}.price", minimum=.01)
            eps = _number(raw.get("eps_ttm"), f"{symbol}.eps_ttm")
            pe = _number(raw.get("pe_ttm"), f"{symbol}.pe_ttm")
            growth = _bounded(raw.get("eps_growth_yoy"), f"{symbol}.eps_growth_yoy", -5, 10)
            target = _number(raw.get("analyst_target_mean"), f"{symbol}.analyst_target_mean", minimum=0)
            sentiment = _bounded(raw.get("news_sentiment"), f"{symbol}.news_sentiment", -1, 1)
            researched_at = _parse_time(raw.get("research_as_of"), f"{symbol}.research_as_of")
            evidence = list(raw.get("evidence") or [])
            if len(evidence) < 2:
                raise SimpleValueInputError(f"{symbol}.evidence requires at least two sources")
            if (now - researched_at).total_seconds() > 7 * 86400:
                raise SimpleValueInputError(f"{symbol} research is more than seven days old")
            reasons = []
            if self.compliance.is_restricted(symbol): reasons.append("RESTRICTED")
            if not raw.get("tradable"): reasons.append("NOT_TRADABLE")
            if eps <= 0: reasons.append("NON_POSITIVE_EPS")
            if pe <= 0 or pe > 25: reasons.append("PE_OUTSIDE_0_TO_25")
            upside = (target / price - 1.0) if target else 0.0
            score = (
                _scale(eps, 0, 15) * .20
                + _scale(pe if pe > 0 else 100, 5, 25, inverse=True) * .35
                + _scale(growth, -.10, .40) * .25
                + _scale(upside, -.15, .30) * .15
                + _scale(sentiment, -1, 1) * .05
            )
            ranked.append({
                **dict(raw), "symbol": symbol, "price": price, "eps_ttm": eps,
                "pe_ttm": pe, "eps_growth_yoy": growth, "analyst_upside": round(upside, 4),
                "value_score": round(score, 2), "eligible": not reasons,
                "rejection_reasons": reasons,
            })
        ranked.sort(key=lambda item: item["value_score"], reverse=True)
        selected = [item for item in ranked if item["eligible"]][:5]
        return {"policy_version": self.policy_version, "shortlist": selected, "all_candidates": ranked}

    def propose_purchase(
        self,
        account: Mapping[str, Any],
        positions: Iterable[Mapping[str, Any]],
        candidates: Iterable[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        account_id = str(account.get("account_id") or account.get("account_number") or "").strip()
        if not account_id:
            raise SimpleValueInputError("account_id is required")
        equity = _number(account.get("portfolio_equity"), "portfolio_equity", minimum=.01)
        cash = min(
            _number(account.get("cash_balance", account.get("cash")), "cash_balance", minimum=0),
            _number(account.get("buying_power"), "buying_power", minimum=0),
        )
        held = {str(item.get("symbol", "")).upper() for item in positions if _number(item.get("quantity"), "quantity", minimum=0) > 0}
        result = self.shortlist(candidates)
        choice = next((item for item in result["shortlist"] if item["symbol"] not in held), None)
        spendable = max(0.0, cash - equity * .10)
        amount = min(spendable, equity * .20)
        reason = None
        intent = None
        if choice is None:
            reason = "NO_ELIGIBLE_UNHELD_CANDIDATE"
        elif amount < 5:
            reason = "INSUFFICIENT_CASH_ABOVE_10_PERCENT_BUFFER"
        elif not choice.get("fractional_tradable") and amount < choice["price"]:
            reason = "INSUFFICIENT_CASH_FOR_WHOLE_SHARE"
        else:
            intent = {
                "symbol": choice["symbol"], "side": "buy", "order_type": "market",
                "market_hours": "regular_hours",
                "reference_price": choice["price"], "target_weight": round(amount / equity, 6),
                "thesis": (
                    f"Positive trailing EPS {choice['eps_ttm']:.2f}, P/E {choice['pe_ttm']:.1f}, "
                    f"EPS growth {choice['eps_growth_yoy']:.1%}, value score {choice['value_score']:.1f}."
                ),
                "evidence": choice["evidence"],
            }
            if choice.get("fractional_tradable"):
                intent["dollar_amount"] = round(amount, 2)
                intent["amount_type"] = "dollar_amount"
            else:
                intent["quantity"] = math.floor(amount / choice["price"])
                intent["amount_type"] = "whole_shares"
        return self._save_plan(account_id, "BUY_PROPOSAL", [intent] if intent else [], reason, result)

    def evaluate_holdings(self, holdings: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
        decisions = []
        for raw in holdings:
            symbol = str(raw.get("symbol", "")).strip().upper()
            eps = _number(raw.get("eps_ttm"), f"{symbol}.eps_ttm")
            prior_eps = _number(raw.get("prior_eps_ttm"), f"{symbol}.prior_eps_ttm")
            pe = _number(raw.get("pe_ttm"), f"{symbol}.pe_ttm")
            sector_pe = _number(raw.get("sector_median_pe"), f"{symbol}.sector_median_pe", minimum=.01)
            surprise = _bounded(raw.get("last_earnings_surprise_pct"), f"{symbol}.last_earnings_surprise_pct", -5, 5)
            target = _number(raw.get("analyst_target_mean"), f"{symbol}.analyst_target_mean", minimum=0)
            price = _number(raw.get("price"), f"{symbol}.price", minimum=.01)
            sentiment = _bounded(raw.get("news_sentiment"), f"{symbol}.news_sentiment", -1, 1)
            evidence = list(raw.get("evidence") or [])
            if len(evidence) < 2:
                raise SimpleValueInputError(f"{symbol}.evidence requires at least two sources")
            researched_at = _parse_time(raw.get("research_as_of"), f"{symbol}.research_as_of")
            if (self.clock().astimezone(timezone.utc) - researched_at).total_seconds() > 7 * 86400:
                raise SimpleValueInputError(f"{symbol} research is more than seven days old")
            signals, severe = [], []
            eps_change = (eps / abs(prior_eps) - 1.0) if prior_eps else 0.0
            if eps <= 0: severe.append("EPS_BECAME_NON_POSITIVE")
            elif eps_change <= -.10: signals.append("EPS_DECLINED_AT_LEAST_10_PERCENT")
            if pe > 35 or pe > sector_pe * 1.5: signals.append("VALUATION_EXPANDED")
            if surprise <= -.10: signals.append("MATERIAL_EARNINGS_MISS")
            guidance = str(raw.get("guidance_direction", "unchanged")).lower()
            if guidance in {"lowered", "withdrawn"}: signals.append("GUIDANCE_DETERIORATED")
            analyst_downside = target / price - 1.0 if target else 0.0
            if analyst_downside <= -.10: signals.append("ANALYST_TARGET_BELOW_PRICE")
            if sentiment <= -.60: signals.append("STRONGLY_NEGATIVE_NEWS")
            if raw.get("material_negative_news"): severe.append("MATERIAL_NEGATIVE_EVENT")
            action = "SELL_REVIEW" if severe or len(signals) >= 2 else "WATCH" if signals else "HOLD"
            decisions.append({
                "symbol": symbol, "action": action, "severe_signals": severe,
                "signals": signals, "eps_change": round(eps_change, 4),
                "analyst_implied_upside": round(analyst_downside, 4),
                "next_earnings_date": raw.get("next_earnings_date"),
                "evidence": evidence,
                "note": "Analyst targets and news are supporting signals, never sole authority.",
            })
        return {"policy_version": self.policy_version, "decisions": decisions}

    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        return self.store.load(plan_id)

    def validate_purchase(self, plan_id: str, account: Mapping[str, Any], quote: Mapping[str, Any]) -> Dict[str, Any]:
        plan = self.store.load(plan_id)
        blockers = []
        if plan.get("plan_type") != "BUY_PROPOSAL" or len(plan.get("order_intents", [])) != 1:
            blockers.append("NO_SINGLE_BUY_INTENT")
            return {"execution_ready": False, "blockers": blockers, "order_intent": None}
        if self.clock().astimezone(timezone.utc) > _parse_time(plan["expires_at"], "expires_at"):
            blockers.append("PLAN_EXPIRED")
        if str(account.get("account_id") or account.get("account_number") or "") != plan["account_id"]:
            blockers.append("ACCOUNT_CHANGED")
        intent = dict(plan["order_intents"][0])
        symbol = intent["symbol"]
        if str(quote.get("symbol", "")).upper() != symbol:
            blockers.append("QUOTE_SYMBOL_MISMATCH")
        fresh_price = _number(quote.get("price"), "quote.price", minimum=.01)
        drift = abs(fresh_price / intent["reference_price"] - 1.0)
        if drift > .05:
            blockers.append("PRICE_DRIFT_OVER_5_PERCENT")
        equity = _number(account.get("portfolio_equity"), "portfolio_equity", minimum=.01)
        cash = min(
            _number(account.get("cash_balance", account.get("cash")), "cash_balance", minimum=0),
            _number(account.get("buying_power"), "buying_power", minimum=0),
        )
        notional = intent.get("dollar_amount", intent.get("quantity", 0) * fresh_price)
        if notional > max(0.0, cash - equity * .10) + .01:
            blockers.append("INSUFFICIENT_CASH_ABOVE_BUFFER")
        intent["fresh_price"] = fresh_price
        return {"execution_ready": not blockers, "blockers": blockers, "order_intent": intent}

    def _save_plan(self, account_id, plan_type, intents, abstention_reason, research):
        created = self.clock().astimezone(timezone.utc).isoformat()
        plan = {
            "schema_version": "2.0", "policy_version": self.policy_version,
            "plan_id": f"plan_{uuid.uuid4().hex}", "plan_type": plan_type,
            "status": "PROPOSED" if intents else "ABSTAINED", "created_at": created,
            "expires_at": (self.clock().astimezone(timezone.utc) + timedelta(hours=24)).isoformat(),
            "account_id": account_id, "order_intents": intents,
            "abstention_reason": abstention_reason, "research": research,
            "execution_instructions": {
                "requires_explicit_user_approval": True,
                "broker": "Robinhood Trading MCP",
                "instruction": "Refresh Robinhood account and quote, review the exact order, then ask for approval before placement.",
            },
        }
        plan["integrity_sha256"] = hashlib.sha256(
            json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.store.save(plan)
        return plan
