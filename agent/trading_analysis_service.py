"""Proposal-only application service for the Trading Analysis MCP server.

This module deliberately has no broker client.  It turns a caller-supplied,
authoritative account snapshot into an expiring trade plan and can revalidate
that plan against a fresh snapshot immediately before the caller reviews it
with a broker.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.compliance import ComplianceEngine
from agent.research_portfolio_pipeline import ResearchPortfolioPipeline
from agent.robinhood_order_contract import OrderContractError, validate_equity_order
from config import DEFAULT_CONFIG, SystemConfig


SCHEMA_VERSION = "1.0"
POLICY_VERSION = "research-portfolio-v5"
PLAN_ID_RE = re.compile(r"^plan_[0-9a-f]{32}$")


class AnalysisInputError(ValueError):
    """Raised when a caller supplies an unsafe or incomplete snapshot."""


class PlanNotFoundError(LookupError):
    """Raised when an immutable plan cannot be found."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise AnalysisInputError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise AnalysisInputError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _finite_positive(value: Any, field: str, *, allow_zero: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AnalysisInputError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0 or (number == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "positive"
        raise AnalysisInputError(f"{field} must be a finite {qualifier} number")
    return number


def _canonical_hash(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class NormalizedSnapshot:
    account_id: str
    portfolio_equity: float
    cash_balance: float
    buying_power: float
    positions: Dict[str, float]
    prices: Dict[str, float]
    market_data_as_of: str


class FilePlanStore:
    """Simple immutable JSON plan store suitable for one server instance."""

    def __init__(self, directory: Optional[Path] = None):
        configured = os.getenv("TRADING_ANALYSIS_PLAN_DIR")
        self.directory = Path(directory or configured or "data/analysis_plans").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, plan: Dict[str, Any]) -> None:
        plan_id = plan["plan_id"]
        if not PLAN_ID_RE.fullmatch(plan_id):
            raise AnalysisInputError("invalid plan identifier")
        path = self.directory / f"{plan_id}.json"
        if path.exists():
            raise AnalysisInputError(f"plan already exists: {plan_id}")
        path.write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")

    def load(self, plan_id: str) -> Dict[str, Any]:
        if not PLAN_ID_RE.fullmatch(plan_id):
            raise AnalysisInputError("invalid plan identifier")
        path = self.directory / f"{plan_id}.json"
        if not path.exists():
            raise PlanNotFoundError(f"unknown plan: {plan_id}")
        return json.loads(path.read_text(encoding="utf-8"))


class TradingAnalysisService:
    """Build and revalidate plans without possessing execution authority."""

    def __init__(
        self,
        config: Optional[SystemConfig] = None,
        store: Optional[FilePlanStore] = None,
        pipeline: Optional[ResearchPortfolioPipeline] = None,
        clock: Callable[[], datetime] = _utc_now,
        plan_ttl_seconds: int = 21_600,
        max_snapshot_age_seconds: int = 900,
        max_price_drift_bps: float = 50.0,
        next_open_max_snapshot_age_seconds: int = 345_600,
        next_open_plan_ttl_seconds: int = 345_600,
        next_open_max_annualized_volatility: float = 0.45,
    ):
        self.config = config or DEFAULT_CONFIG
        self.compliance = ComplianceEngine(self.config.compliance)
        self.pipeline = pipeline or ResearchPortfolioPipeline(
            config=self.config,
            compliance=self.compliance,
        )
        self.store = store or FilePlanStore()
        self.clock = clock
        self.plan_ttl_seconds = plan_ttl_seconds
        self.max_snapshot_age_seconds = max_snapshot_age_seconds
        self.max_price_drift_bps = max_price_drift_bps
        self.next_open_max_snapshot_age_seconds = next_open_max_snapshot_age_seconds
        self.next_open_plan_ttl_seconds = next_open_plan_ttl_seconds
        self.next_open_max_annualized_volatility = next_open_max_annualized_volatility

    def get_strategy_policy(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "service_role": "analysis_and_proposals_only",
            "can_execute_orders": False,
            "restricted_tickers": sorted(self.compliance.restricted_tickers),
            "max_position_weight": self.config.compliance.max_position_weight,
            "position_policy": (
                "max_position_weight is the hard ceiling. A mandate may set a stricter "
                "maximum_position_weight; the documented workflow uses 0.20."
            ),
            "minimum_cash_buffer": self.config.compliance.min_cash_buffer,
            "default_target_cash_weight": 0.10,
            "legacy_advisory_target_cash_buffer": self.config.compliance.target_cash_buffer,
            "cash_policy": (
                "minimum_cash_buffer is enforced. default_target_cash_weight is the dynamic pipeline "
                "default. legacy_advisory_target_cash_buffer is not enforced and may be overridden."
            ),
            "plan_ttl_seconds": self.plan_ttl_seconds,
            "maximum_quote_age_seconds": self.max_snapshot_age_seconds,
            "planning_modes": {
                "immediate": {
                    "maximum_snapshot_age_seconds": self.max_snapshot_age_seconds,
                    "plan_ttl_seconds": self.plan_ttl_seconds,
                },
                "next_market_open": {
                    "maximum_snapshot_age_seconds": self.next_open_max_snapshot_age_seconds,
                    "plan_ttl_seconds": self.next_open_plan_ttl_seconds,
                    "maximum_annualized_volatility": self.next_open_max_annualized_volatility,
                    "requires_fresh_pre_execution_validation": True,
                },
            },
            "maximum_price_drift_bps": self.max_price_drift_bps,
            "expiration_is_hard_blocker": True,
            "equity_order_contract": {
                "fractional_purchase": "regular-hours market order",
                "dollar_purchase": "regular-hours market order",
                "limit_order": "whole shares only; whole-cent price above $1",
                "fractional_or_dollar_outside_regular_hours": "invalid",
            },
            "candidate_universe": "dynamic; supplied by ChatGPT Work with evidence",
            "portfolio_engine": "multi_factor_research_and_mandate_driven",
            "fractional_share_sizing": True,
            "accepted_mandate_fields": [
                "objective", "risk_tolerance", "time_horizon_months", "target_cash_weight",
                "maximum_position_weight", "maximum_sector_weight", "maximum_positions",
                "minimum_candidate_score", "minimum_trade_notional",
                "minimum_average_dollar_volume", "maximum_annualized_volatility",
                "allow_fractional_shares", "allowed_asset_types", "excluded_sectors",
                "factor_weights",
            ],
            "execution_owner": "ChatGPT Work using the separately authenticated Robinhood Trading MCP",
        }

    def get_research_requirements(self) -> Dict[str, Any]:
        """Describe the structured evidence ChatGPT Work must gather."""
        return self.pipeline.research_requirements()

    def _normalize_snapshot(
        self,
        account: Dict[str, Any],
        positions: List[Dict[str, Any]],
        quotes: List[Dict[str, Any]],
        market_data_as_of: str,
        maximum_age_seconds: Optional[int] = None,
    ) -> NormalizedSnapshot:
        as_of = _parse_timestamp(market_data_as_of, "market_data_as_of")
        age = (self.clock().astimezone(timezone.utc) - as_of).total_seconds()
        if age < -60:
            raise AnalysisInputError("market_data_as_of cannot be in the future")
        maximum_age = self.max_snapshot_age_seconds if maximum_age_seconds is None else maximum_age_seconds
        if age > maximum_age:
            raise AnalysisInputError(
                f"market snapshot is stale ({int(age)}s old; maximum is "
                f"{maximum_age}s)"
            )

        equity = _finite_positive(account.get("portfolio_equity"), "account.portfolio_equity")
        cash = _finite_positive(account.get("cash_balance", account.get("cash")), "account.cash_balance", allow_zero=True)
        buying_power = _finite_positive(account.get("buying_power"), "account.buying_power", allow_zero=True)
        account_id = str(account.get("account_id") or account.get("account_number") or "").strip()
        if not account_id:
            raise AnalysisInputError("account.account_id is required")

        price_map: Dict[str, float] = {}
        for item in quotes:
            symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            if not symbol:
                raise AnalysisInputError("every quote requires symbol")
            price_map[symbol] = _finite_positive(
                item.get("price", item.get("last_trade_price")),
                f"quote[{symbol}].price",
            )

        holding_map: Dict[str, float] = {}
        for item in positions:
            symbol = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            if not symbol:
                raise AnalysisInputError("every position requires symbol")
            raw_quantity = item.get("quantity")
            try:
                quantity_float = float(raw_quantity)
            except (TypeError, ValueError) as exc:
                raise AnalysisInputError(f"position[{symbol}].quantity must be numeric") from exc
            if not math.isfinite(quantity_float) or quantity_float < 0:
                raise AnalysisInputError(f"position[{symbol}].quantity must be finite and non-negative")
            holding_map[symbol] = quantity_float
            if symbol not in price_map:
                fallback = item.get("current_price")
                if fallback is None:
                    raise AnalysisInputError(f"a current quote is required for held symbol {symbol}")
                price_map[symbol] = _finite_positive(fallback, f"position[{symbol}].current_price")

        return NormalizedSnapshot(
            account_id=account_id,
            portfolio_equity=equity,
            cash_balance=cash,
            buying_power=buying_power,
            positions=holding_map,
            prices=price_map,
            market_data_as_of=as_of.isoformat(),
        )

    def generate_trade_plan(
        self,
        account: Dict[str, Any],
        positions: List[Dict[str, Any]],
        research_candidates: List[Dict[str, Any]],
        market_data_as_of: str,
        mandate: Optional[Dict[str, Any]] = None,
        planning_mode: str = "immediate",
        market_session: str = "regular_hours",
    ) -> Dict[str, Any]:
        if planning_mode not in {"immediate", "next_market_open"}:
            raise AnalysisInputError("planning_mode must be immediate or next_market_open")
        if market_session not in {"regular_hours", "extended_hours", "closed"}:
            raise AnalysisInputError("market_session must be regular_hours, extended_hours, or closed")
        if planning_mode == "immediate" and market_session != "regular_hours":
            raise AnalysisInputError(
                "planning_mode=immediate is valid only during regular_hours; "
                "use next_market_open outside the regular session"
            )
        effective_mandate = dict(mandate or {})
        if planning_mode == "next_market_open":
            try:
                requested_volatility = float(
                    effective_mandate.get(
                        "maximum_annualized_volatility", self.next_open_max_annualized_volatility
                    )
                )
            except (TypeError, ValueError) as exc:
                raise AnalysisInputError("mandate.maximum_annualized_volatility must be numeric") from exc
            effective_mandate["maximum_annualized_volatility"] = min(
                requested_volatility, self.next_open_max_annualized_volatility
            )
        quotes = [
            {"symbol": item.get("symbol"), "price": item.get("price")}
            for item in research_candidates
        ]
        snapshot = self._normalize_snapshot(
            account,
            positions,
            quotes,
            market_data_as_of,
            maximum_age_seconds=(
                self.next_open_max_snapshot_age_seconds
                if planning_mode == "next_market_open"
                else self.max_snapshot_age_seconds
            ),
        )
        constructed = self.pipeline.construct_portfolio(
            candidates=research_candidates,
            mandate_raw=effective_mandate,
            positions=snapshot.positions,
            portfolio_equity=snapshot.portfolio_equity,
            available_cash=min(snapshot.cash_balance, snapshot.buying_power),
            now=self.clock().astimezone(timezone.utc),
        )

        created_at = self.clock().astimezone(timezone.utc)
        plan_ttl = self.next_open_plan_ttl_seconds if planning_mode == "next_market_open" else self.plan_ttl_seconds
        expires_at = created_at + timedelta(seconds=plan_ttl)
        plan_id = f"plan_{uuid.uuid4().hex}"
        order_intents = []
        for index, intent in enumerate(constructed["order_intents"]):
            frozen_intent = {
                "intent_id": f"{plan_id}:{index + 1}",
                "idempotency_key": str(uuid.uuid4()),
                **intent,
            }
            try:
                validate_equity_order(frozen_intent, require_idempotency=True)
            except OrderContractError as exc:
                raise AnalysisInputError(f"invalid generated order for {intent.get('symbol')}: {exc}") from exc
            order_intents.append(frozen_intent)

        plan: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "policy_version": POLICY_VERSION,
            "plan_id": plan_id,
            "status": "PROPOSED",
            "planning_mode": planning_mode,
            "market_session_at_creation": market_session,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "account_snapshot": asdict(snapshot),
            "mandate": asdict(constructed["mandate"]),
            "ranked_candidates": constructed["ranked_candidates"],
            "selected_symbols": constructed["selected_symbols"],
            "target_weights": constructed["target_weights"],
            "sector_weights": constructed["sector_weights"],
            "abstained": constructed["abstained"],
            "abstention_reason": constructed["abstention_reason"],
            "warnings": (
                ["AFTER_HOURS_REFERENCE_PRICES", "DO_NOT_EXECUTE_WITHOUT_FRESH_MARKET_OPEN_REVALIDATION"]
                if planning_mode == "next_market_open"
                else []
            ),
            "order_intents": order_intents,
            "execution_instructions": {
                "requires_explicit_user_approval": True,
                "approval_prompt": (
                    f"Do you approve plan {plan_id} for pre-execution revalidation and Robinhood order review?"
                ),
                "required_next_step": (
                    "At market open, call validate_trade_plan with fresh Robinhood account data and quotes; "
                    "only then proceed to Robinhood review tools."
                    if planning_mode == "next_market_open"
                    else "Call validate_trade_plan with fresh Robinhood data, then call Robinhood review tools."
                ),
                "broker": "Robinhood Trading MCP",
            },
        }
        plan["integrity_sha256"] = _canonical_hash(plan)
        self.store.save(plan)
        return plan

    def get_trade_plan(self, plan_id: str) -> Dict[str, Any]:
        return self.store.load(plan_id)

    def validate_trade_plan(
        self,
        plan_id: str,
        account: Dict[str, Any],
        positions: List[Dict[str, Any]],
        quotes: List[Dict[str, Any]],
        market_data_as_of: str,
        market_session: str = "regular_hours",
    ) -> Dict[str, Any]:
        plan = self.store.load(plan_id)
        integrity = plan.get("integrity_sha256")
        unsigned = dict(plan)
        unsigned.pop("integrity_sha256", None)
        if integrity != _canonical_hash(unsigned):
            raise RuntimeError("stored plan failed integrity validation")

        snapshot = self._normalize_snapshot(account, positions, quotes, market_data_as_of)
        now = self.clock().astimezone(timezone.utc)
        blockers: List[str] = []
        warnings: List[str] = []

        expires_at = _parse_timestamp(plan["expires_at"], "expires_at")
        if now > expires_at:
            blockers.append("PLAN_EXPIRED")
        if market_session not in {"regular_hours", "extended_hours", "closed"}:
            blockers.append("INVALID_MARKET_SESSION")
        if plan.get("planning_mode") == "next_market_open" and market_session != "regular_hours":
            blockers.append("MARKET_NOT_OPEN_FOR_NEXT_OPEN_PLAN")
        original = plan["account_snapshot"]
        if snapshot.account_id != original["account_id"]:
            blockers.append("ACCOUNT_CHANGED")
        equity_drift = abs(snapshot.portfolio_equity - float(original["portfolio_equity"])) / float(original["portfolio_equity"])
        if equity_drift > 0.05:
            blockers.append("PORTFOLIO_EQUITY_CHANGED_OVER_5_PERCENT")

        buy_notional = 0.0
        sell_notional = 0.0
        broker_review_intents = []
        for intent in plan["order_intents"]:
            symbol = intent["symbol"]
            if self.compliance.is_restricted(symbol):
                blockers.append(f"RESTRICTED_SYMBOL:{symbol}")
                continue
            fresh_price = snapshot.prices.get(symbol)
            if fresh_price is None:
                blockers.append(f"MISSING_FRESH_QUOTE:{symbol}")
                continue
            planned_reference = float(intent.get("reference_price", intent.get("limit_price")))
            drift_bps = abs(fresh_price - planned_reference) / planned_reference * 10_000
            if drift_bps > self.max_price_drift_bps:
                blockers.append(f"PRICE_DRIFT:{symbol}:{drift_bps:.1f}_BPS")

            try:
                validated_order = validate_equity_order(
                    {**intent, "market_hours": market_session}, require_idempotency=True
                )
            except OrderContractError as exc:
                blockers.append(f"ORDER_CONTRACT:{symbol}:{exc}")
                continue
            quantity = validated_order.quantity
            notional = (
                float(validated_order.dollar_amount)
                if validated_order.dollar_amount is not None
                else float(quantity) * fresh_price
            )
            if intent["side"] == "sell":
                if quantity is None or quantity > snapshot.positions.get(symbol, 0):
                    blockers.append(f"INSUFFICIENT_POSITION:{symbol}")
                sell_notional += notional
            else:
                buy_notional += notional
                resulting_value = snapshot.positions.get(symbol, 0) * fresh_price + notional
                plan_position_cap = min(
                    float(plan["mandate"]["maximum_position_weight"]),
                    self.config.compliance.max_position_weight,
                )
                if resulting_value / snapshot.portfolio_equity > plan_position_cap:
                    blockers.append(f"POSITION_CAP_EXCEEDED:{symbol}")

            broker_review_intents.append({
                "intent_id": intent["intent_id"],
                **validated_order.as_dict(),
                "fresh_reference_price": fresh_price,
            })

        if buy_notional > snapshot.buying_power + sell_notional:
            blockers.append("INSUFFICIENT_BUYING_POWER")
        projected_cash = snapshot.cash_balance + sell_notional - buy_notional
        if projected_cash / snapshot.portfolio_equity < self.config.compliance.min_cash_buffer:
            blockers.append("MINIMUM_CASH_BUFFER_VIOLATION")
        if snapshot.positions != original["positions"]:
            warnings.append("POSITIONS_CHANGED_SINCE_PLAN_CREATION")

        unique_blockers = list(dict.fromkeys(blockers))
        return {
            "schema_version": SCHEMA_VERSION,
            "plan_id": plan_id,
            "validated_at": now.isoformat(),
            "execution_ready": not unique_blockers and bool(broker_review_intents),
            "blockers": unique_blockers,
            "warnings": warnings,
            "broker_review_intents": broker_review_intents if not unique_blockers else [],
            "required_next_step": (
                "Call Robinhood review_equity_order for every exact broker_review_intent. If every review "
                "has no validation alert, present the reviews and require a second explicit authorization "
                "identifying this plan ID before placement."
                if not unique_blockers and broker_review_intents
                else "Do not execute. Resolve non-expiration blockers or, under new user direction, generate a new plan."
            ),
            "second_approval_prompt": (
                f"Robinhood has reviewed the exact orders for plan {plan_id}. Do you authorize "
                "submission of these reviewed orders?"
                if not unique_blockers and broker_review_intents
                else None
            ),
            "can_execute_orders": False,
        }
