"""Mandate-driven research and portfolio-construction pipeline.

ChatGPT Work performs discovery and research with its available tools, then
submits structured evidence packets here.  This module validates those packets,
scores candidates consistently, constructs a portfolio, and creates order
intents.  It never talks to a broker.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional

from agent.compliance import ComplianceEngine
from config import DEFAULT_CONFIG, SystemConfig


SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


class ResearchInputError(ValueError):
    """Raised when research cannot safely support portfolio construction."""


def _number(value: Any, field_name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ResearchInputError(f"{field_name} must be numeric") from exc
    if not math.isfinite(result):
        raise ResearchInputError(f"{field_name} must be finite")
    return result


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _scale(value: float, low: float, high: float, *, inverse: bool = False) -> float:
    if high <= low:
        return 50.0
    score = _clamp((value - low) / (high - low) * 100.0)
    return 100.0 - score if inverse else score


def _parse_time(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ResearchInputError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ResearchInputError(f"{field_name} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass
class InvestmentMandate:
    objective: str = "long_term_total_return"
    risk_tolerance: str = "moderate"
    time_horizon_months: int = 36
    target_cash_weight: float = 0.10
    maximum_position_weight: float = 0.20
    maximum_sector_weight: float = 0.35
    maximum_positions: int = 10
    minimum_candidate_score: float = 60.0
    minimum_trade_notional: float = 5.0
    minimum_average_dollar_volume: float = 5_000_000.0
    maximum_annualized_volatility: float = 1.0
    allow_fractional_shares: bool = True
    allowed_asset_types: List[str] = field(default_factory=lambda: ["equity", "etf"])
    excluded_sectors: List[str] = field(default_factory=list)
    factor_weights: Dict[str, float] = field(default_factory=lambda: {
        "quality": 0.20,
        "growth": 0.20,
        "valuation": 0.15,
        "momentum": 0.20,
        "catalyst": 0.10,
        "risk": 0.15,
    })

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]], config: SystemConfig) -> "InvestmentMandate":
        raw = dict(raw or {})
        known = {name for name in cls.__dataclass_fields__}
        unknown = sorted(set(raw).difference(known))
        if unknown:
            raise ResearchInputError("unknown mandate fields: " + ", ".join(unknown))
        mandate = cls(**raw)
        mandate.target_cash_weight = _number(mandate.target_cash_weight, "target_cash_weight")
        mandate.maximum_position_weight = min(
            _number(mandate.maximum_position_weight, "maximum_position_weight"),
            config.compliance.max_position_weight,
        )
        mandate.maximum_sector_weight = _number(mandate.maximum_sector_weight, "maximum_sector_weight")
        mandate.minimum_candidate_score = _number(mandate.minimum_candidate_score, "minimum_candidate_score")
        mandate.minimum_trade_notional = _number(mandate.minimum_trade_notional, "minimum_trade_notional")
        mandate.minimum_average_dollar_volume = _number(
            mandate.minimum_average_dollar_volume, "minimum_average_dollar_volume"
        )
        mandate.maximum_annualized_volatility = _number(
            mandate.maximum_annualized_volatility, "maximum_annualized_volatility"
        )
        if not 0.05 <= mandate.target_cash_weight <= 0.80:
            raise ResearchInputError("target_cash_weight must be between 5% and 80%")
        if not 0.01 <= mandate.maximum_position_weight <= 0.25:
            raise ResearchInputError("maximum_position_weight must be between 1% and 25%")
        if not mandate.maximum_position_weight <= mandate.maximum_sector_weight <= 1.0:
            raise ResearchInputError("maximum_sector_weight must be at least maximum_position_weight")
        if not 1 <= int(mandate.maximum_positions) <= 50:
            raise ResearchInputError("maximum_positions must be between 1 and 50")
        if not 0.05 <= mandate.maximum_annualized_volatility <= 2.0:
            raise ResearchInputError("maximum_annualized_volatility must be between 5% and 200%")
        mandate.maximum_positions = int(mandate.maximum_positions)
        if mandate.risk_tolerance not in {"conservative", "moderate", "aggressive"}:
            raise ResearchInputError("risk_tolerance must be conservative, moderate, or aggressive")
        mandate.time_horizon_months = int(mandate.time_horizon_months)
        if not 1 <= mandate.time_horizon_months <= 600:
            raise ResearchInputError("time_horizon_months must be between 1 and 600")
        if "factor_weights" not in raw:
            if mandate.risk_tolerance == "conservative":
                mandate.factor_weights = {
                    "quality": .25, "growth": .15, "valuation": .15,
                    "momentum": .10, "catalyst": .05, "risk": .30,
                }
                mandate.maximum_position_weight = min(mandate.maximum_position_weight, .15)
                mandate.maximum_sector_weight = min(mandate.maximum_sector_weight, .30)
            elif mandate.risk_tolerance == "aggressive":
                mandate.factor_weights = {
                    "quality": .15, "growth": .25, "valuation": .10,
                    "momentum": .25, "catalyst": .15, "risk": .10,
                }
            if mandate.time_horizon_months >= 60:
                mandate.factor_weights["quality"] += .05
                mandate.factor_weights["valuation"] += .03
                mandate.factor_weights["momentum"] = max(0, mandate.factor_weights["momentum"] - .05)
                mandate.factor_weights["catalyst"] = max(0, mandate.factor_weights["catalyst"] - .03)
            elif mandate.time_horizon_months <= 12:
                mandate.factor_weights["momentum"] += .05
                mandate.factor_weights["catalyst"] += .03
                mandate.factor_weights["quality"] = max(0, mandate.factor_weights["quality"] - .05)
                mandate.factor_weights["valuation"] = max(0, mandate.factor_weights["valuation"] - .03)
        weights = {key: _number(value, f"factor_weights.{key}") for key, value in mandate.factor_weights.items()}
        required = {"quality", "growth", "valuation", "momentum", "catalyst", "risk"}
        if set(weights) != required or sum(weights.values()) <= 0:
            raise ResearchInputError("factor_weights must contain all six supported factors")
        total = sum(weights.values())
        mandate.factor_weights = {key: value / total for key, value in weights.items()}
        mandate.allowed_asset_types = [str(item).lower() for item in mandate.allowed_asset_types]
        mandate.excluded_sectors = [str(item).lower() for item in mandate.excluded_sectors]
        return mandate


class ResearchPortfolioPipeline:
    """Validate research, score opportunities, and construct target weights."""

    def __init__(
        self,
        config: Optional[SystemConfig] = None,
        compliance: Optional[ComplianceEngine] = None,
        maximum_research_age_days: int = 14,
    ):
        self.config = config or DEFAULT_CONFIG
        self.compliance = compliance or ComplianceEngine(self.config.compliance)
        self.maximum_research_age_days = maximum_research_age_days

    def research_requirements(self) -> Dict[str, Any]:
        return {
            "candidate_discovery": (
                "ChatGPT Work should use a research provider such as Rallies to screen a broad, dynamic "
                "universe. Model portfolios, community portfolios, watchlists, and current holdings may "
                "seed discovery but must not become the target portfolio without independent scoring."
            ),
            "source_authority": {
                "robinhood": [
                    "account_id", "portfolio_equity", "cash_balance", "buying_power",
                    "positions", "price", "tradable", "fractional_tradable",
                ],
                "research_provider": [
                    "sector", "fundamentals", "technical", "catalysts", "risk", "evidence",
                ],
                "chatgpt_work": ["thesis", "agent_conviction"],
            },
            "provider_guidance": {
                "rallies": (
                    "Use for screening and research when connected. Treat Rallies model portfolios, "
                    "AI Arena results, community sentiment, options flow, and dark-pool activity as "
                    "candidate or supplemental signals, not trade instructions."
                ),
                "conflict_rule": (
                    "Robinhood is authoritative for account, position, tradability, fractional eligibility, "
                    "and executable price fields. Do not substitute a research-provider quote for the "
                    "Robinhood price submitted to generate_trade_plan."
                ),
            },
            "required_candidate_fields": [
                "symbol", "asset_type", "sector", "tradable", "fractional_tradable",
                "price", "research_as_of", "thesis", "evidence", "fundamentals",
                "technical", "catalysts", "risk",
            ],
            "required_fundamentals": [
                "revenue_growth", "earnings_growth", "free_cash_flow_margin",
                "return_on_equity", "forward_pe", "peg_ratio",
            ],
            "required_technical": ["return_20d", "return_60d", "above_sma_200"],
            "required_catalysts": ["score", "sentiment"],
            "required_risk": ["annualized_volatility", "max_drawdown", "beta", "average_dollar_volume"],
            "evidence_requirement": (
                "At least two distinct source records with URL/title and observed_at. Prefer a primary "
                "filing or issuer source for material fundamental claims; provider-generated summaries "
                "and social/community signals alone are insufficient."
            ),
            "restricted_tickers": sorted(self.compliance.restricted_tickers),
            "maximum_research_age_days": self.maximum_research_age_days,
        }

    def _score_candidate(self, raw: Mapping[str, Any], now: datetime, mandate: InvestmentMandate) -> Dict[str, Any]:
        symbol = str(raw.get("symbol", "")).strip().upper()
        if not SYMBOL_RE.fullmatch(symbol):
            raise ResearchInputError(f"invalid symbol: {symbol or '<empty>'}")
        if self.compliance.is_restricted(symbol):
            return {"symbol": symbol, "eligible": False, "rejection_reasons": ["RESTRICTED_SECURITY"]}

        rejection_reasons: List[str] = []
        asset_type = str(raw.get("asset_type", "equity")).lower()
        sector = str(raw.get("sector", "unknown")).strip().lower()
        if asset_type not in mandate.allowed_asset_types:
            rejection_reasons.append("ASSET_TYPE_NOT_ALLOWED")
        if sector in mandate.excluded_sectors:
            rejection_reasons.append("SECTOR_EXCLUDED")
        if raw.get("tradable") is not True:
            rejection_reasons.append("NOT_TRADABLE")

        price = _number(raw.get("price"), f"{symbol}.price")
        if price <= 0:
            rejection_reasons.append("INVALID_PRICE")
        researched_at = _parse_time(str(raw.get("research_as_of", "")), f"{symbol}.research_as_of")
        age_days = (now - researched_at).total_seconds() / 86400
        if age_days < -1 / 24 or age_days > self.maximum_research_age_days:
            rejection_reasons.append("RESEARCH_STALE_OR_FUTURE_DATED")

        evidence = raw.get("evidence") or []
        valid_evidence = []
        seen_urls = set()
        for item in evidence:
            if not isinstance(item, Mapping) or not item.get("url") or not item.get("title") or not item.get("observed_at"):
                continue
            try:
                observed_at = _parse_time(str(item["observed_at"]), f"{symbol}.evidence.observed_at")
            except ResearchInputError:
                continue
            evidence_age = (now - observed_at).total_seconds() / 86400
            url = str(item["url"])
            if -1 / 24 <= evidence_age <= self.maximum_research_age_days and url not in seen_urls:
                valid_evidence.append(dict(item))
                seen_urls.add(url)
        if len(valid_evidence) < 2:
            rejection_reasons.append("INSUFFICIENT_EVIDENCE")

        f = raw.get("fundamentals") or {}
        t = raw.get("technical") or {}
        c = raw.get("catalysts") or {}
        r = raw.get("risk") or {}
        required_groups = {
            "fundamentals": (f, ["revenue_growth", "earnings_growth", "free_cash_flow_margin", "return_on_equity", "forward_pe", "peg_ratio"]),
            "technical": (t, ["return_20d", "return_60d", "above_sma_200"]),
            "catalysts": (c, ["score", "sentiment"]),
            "risk": (r, ["annualized_volatility", "max_drawdown", "beta", "average_dollar_volume"]),
        }
        missing = [f"{group}.{field}" for group, (values, fields) in required_groups.items() for field in fields if field not in values]
        if missing:
            raise ResearchInputError(f"{symbol} is missing research fields: " + ", ".join(missing))

        average_dollar_volume = _number(r["average_dollar_volume"], f"{symbol}.risk.average_dollar_volume")
        if average_dollar_volume < mandate.minimum_average_dollar_volume:
            rejection_reasons.append("INSUFFICIENT_LIQUIDITY")
        annualized_volatility = _number(r["annualized_volatility"], f"{symbol}.risk.annualized_volatility")
        if annualized_volatility > mandate.maximum_annualized_volatility:
            rejection_reasons.append("EXCESSIVE_VOLATILITY")

        quality = (
            _scale(_number(f["free_cash_flow_margin"], "free_cash_flow_margin"), -0.10, 0.35) * 0.55
            + _scale(_number(f["return_on_equity"], "return_on_equity"), -0.10, 0.40) * 0.45
        )
        growth = (
            _scale(_number(f["revenue_growth"], "revenue_growth"), -0.20, 0.50) * 0.50
            + _scale(_number(f["earnings_growth"], "earnings_growth"), -0.30, 0.60) * 0.50
        )
        valuation = (
            _scale(_number(f["forward_pe"], "forward_pe"), 8.0, 60.0, inverse=True) * 0.55
            + _scale(_number(f["peg_ratio"], "peg_ratio"), 0.5, 4.0, inverse=True) * 0.45
        )
        momentum = (
            _scale(_number(t["return_20d"], "return_20d"), -0.20, 0.25) * 0.45
            + _scale(_number(t["return_60d"], "return_60d"), -0.30, 0.50) * 0.40
            + (100.0 if bool(t["above_sma_200"]) else 0.0) * 0.15
        )
        catalyst = (
            _clamp(_number(c["score"], "catalysts.score")) * 0.70
            + _scale(_number(c["sentiment"], "catalysts.sentiment"), -1.0, 1.0) * 0.30
        )
        risk = (
            _scale(annualized_volatility, 0.10, 0.90, inverse=True) * 0.40
            + _scale(abs(_number(r["max_drawdown"], "max_drawdown")), 0.05, 0.65, inverse=True) * 0.35
            + _scale(_number(r["beta"], "beta"), 0.5, 2.0, inverse=True) * 0.25
        )
        factors = {
            "quality": quality, "growth": growth, "valuation": valuation,
            "momentum": momentum, "catalyst": catalyst, "risk": risk,
        }
        composite = sum(factors[name] * mandate.factor_weights[name] for name in factors)
        evidence_confidence = min(1.0, len(valid_evidence) / 4.0)
        freshness_confidence = _clamp(1.0 - max(0.0, age_days) / self.maximum_research_age_days, 0.0, 1.0)
        confidence = 0.55 * evidence_confidence + 0.45 * freshness_confidence
        conviction = _clamp(_number(raw.get("agent_conviction", 50.0), "agent_conviction"))
        adjusted_score = composite * (0.75 + 0.25 * confidence) * (0.90 + 0.10 * conviction / 100.0)
        if adjusted_score < mandate.minimum_candidate_score:
            rejection_reasons.append("BELOW_MINIMUM_SCORE")

        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "sector": sector,
            "price": round(price, 6),
            "fractional_tradable": bool(raw.get("fractional_tradable")),
            "eligible": not rejection_reasons,
            "rejection_reasons": rejection_reasons,
            "factor_scores": {name: round(value, 2) for name, value in factors.items()},
            "composite_score": round(composite, 2),
            "confidence": round(confidence, 3),
            "adjusted_score": round(adjusted_score, 2),
            "thesis": str(raw.get("thesis", "")).strip(),
            "evidence": valid_evidence,
            "research_as_of": researched_at.isoformat(),
        }

    def screen_candidates(
        self,
        candidates: Iterable[Mapping[str, Any]],
        mandate_raw: Optional[Mapping[str, Any]],
        now: datetime,
    ) -> Dict[str, Any]:
        mandate = InvestmentMandate.from_mapping(mandate_raw, self.config)
        seen = set()
        scored = []
        for raw in candidates:
            symbol = str(raw.get("symbol", "")).strip().upper()
            if symbol in seen:
                raise ResearchInputError(f"duplicate candidate: {symbol}")
            seen.add(symbol)
            scored.append(self._score_candidate(raw, now, mandate))
        ranked = sorted(scored, key=lambda item: item.get("adjusted_score", -1), reverse=True)
        return {"mandate": mandate, "ranked_candidates": ranked}

    def construct_portfolio(
        self,
        candidates: List[Mapping[str, Any]],
        mandate_raw: Optional[Mapping[str, Any]],
        positions: Mapping[str, float],
        portfolio_equity: float,
        available_cash: float,
        now: datetime,
    ) -> Dict[str, Any]:
        screened = self.screen_candidates(candidates, mandate_raw, now)
        mandate: InvestmentMandate = screened["mandate"]
        ranked = screened["ranked_candidates"]
        candidate_symbols = {item["symbol"] for item in ranked}
        uncovered = sorted(symbol for symbol, quantity in positions.items() if quantity > 0 and symbol not in candidate_symbols)
        if uncovered:
            raise ResearchInputError(
                "research packets are required for every current holding; missing: " + ", ".join(uncovered)
            )

        eligible = [item for item in ranked if item["eligible"]][:mandate.maximum_positions]
        target_weights: Dict[str, float] = {}
        sector_weights: Dict[str, float] = {}
        remaining = 1.0 - mandate.target_cash_weight
        remaining_score = sum(item["adjusted_score"] for item in eligible)
        pending = list(eligible)
        while pending and remaining > 1e-8 and remaining_score > 0:
            progress = False
            for item in list(pending):
                proportional = remaining * item["adjusted_score"] / remaining_score
                sector_room = mandate.maximum_sector_weight - sector_weights.get(item["sector"], 0.0)
                weight = max(0.0, min(proportional, mandate.maximum_position_weight, sector_room))
                if weight > 0:
                    target_weights[item["symbol"]] = weight
                    sector_weights[item["sector"]] = sector_weights.get(item["sector"], 0.0) + weight
                    remaining -= weight
                    progress = True
                remaining_score -= item["adjusted_score"]
                pending.remove(item)
            if not progress:
                break
        target_weights["CASH"] = mandate.target_cash_weight + max(0.0, remaining)

        intents: List[Dict[str, Any]] = []
        selected_by_symbol = {item["symbol"]: item for item in eligible}
        scored_by_symbol = {item["symbol"]: item for item in ranked}
        all_symbols = set(scored_by_symbol).union(positions)
        for symbol in sorted(all_symbols):
            item = scored_by_symbol[symbol]
            if self.compliance.is_restricted(symbol):
                continue
            price = item["price"]
            current_quantity = float(positions.get(symbol, 0.0))
            current_value = current_quantity * price
            target_value = target_weights.get(symbol, 0.0) * portfolio_equity
            delta = target_value - current_value
            if abs(delta) < mandate.minimum_trade_notional or abs(delta) / portfolio_equity < 0.01:
                continue
            side = "buy" if delta > 0 else "sell"
            desired_notional = abs(delta)
            if side == "sell":
                desired_notional = min(desired_notional, current_value)
            fractional = mandate.allow_fractional_shares and item.get("fractional_tradable", False)
            if fractional:
                quantity = round(desired_notional / price, 6)
                notional = round(quantity * price, 2)
                amount_type = "fractional_shares"
            else:
                quantity = math.floor(desired_notional / price)
                notional = round(quantity * price, 2)
                amount_type = "whole_shares"
            if quantity <= 0 or notional < mandate.minimum_trade_notional:
                continue
            intents.append({
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "amount_type": amount_type,
                "order_type": "limit",
                "limit_price": price,
                "estimated_notional": notional,
                "current_weight": round(current_value / portfolio_equity, 6),
                "target_weight": round(target_weights.get(symbol, 0.0), 6),
                "sector": item["sector"],
                "adjusted_score": item.get("adjusted_score"),
                "thesis": item.get("thesis", ""),
                "evidence": item.get("evidence", []),
            })

        sells = sum(item["estimated_notional"] for item in intents if item["side"] == "sell")
        buys = sum(item["estimated_notional"] for item in intents if item["side"] == "buy")
        maximum_spend = max(0.0, available_cash + sells - portfolio_equity * mandate.target_cash_weight)
        if buys > maximum_spend and buys > 0:
            scale = maximum_spend / buys
            resized = []
            for item in intents:
                if item["side"] != "buy":
                    resized.append(item)
                    continue
                desired = item["estimated_notional"] * scale
                if item["amount_type"] == "fractional_shares":
                    item["quantity"] = round(desired / item["limit_price"], 6)
                else:
                    item["quantity"] = math.floor(desired / item["limit_price"])
                item["estimated_notional"] = round(item["quantity"] * item["limit_price"], 2)
                if item["quantity"] > 0 and item["estimated_notional"] >= mandate.minimum_trade_notional:
                    resized.append(item)
            intents = resized

        return {
            "mandate": mandate,
            "ranked_candidates": ranked,
            "selected_symbols": list(selected_by_symbol),
            "target_weights": {key: round(value, 6) for key, value in target_weights.items()},
            "sector_weights": {key: round(value, 6) for key, value in sector_weights.items()},
            "order_intents": intents,
            "abstained": not intents,
            "abstention_reason": "NO_TRADE_CLEARED_RESEARCH_AND_SIZING_THRESHOLDS" if not intents else None,
        }
