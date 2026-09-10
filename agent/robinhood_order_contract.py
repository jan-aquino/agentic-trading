"""Shared Robinhood-compatible equity order validation.

This is used by local review and placement adapters so deterministic broker
contract failures are rejected before either stage reports success.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Dict, Optional


class OrderContractError(ValueError):
    """Raised when an equity order cannot be represented by Robinhood."""


@dataclass(frozen=True)
class ValidatedEquityOrder:
    symbol: str
    side: str
    order_type: str
    amount_type: str
    market_hours: str
    quantity: Optional[float] = None
    dollar_amount: Optional[float] = None
    limit_price: Optional[float] = None
    reference_price: Optional[float] = None
    idempotency_key: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if value is not None}


def select_cent_limit(reference_price: float, side: str) -> float:
    """Select a broker-valid limit without rewriting the observed quote.

    For prices above $1, buy limits round up to the nearest cent and sell
    limits round down. At or below $1, four decimal places are retained.
    """
    price = Decimal(str(reference_price))
    if not price.is_finite() or price <= 0:
        raise OrderContractError("reference_price must be a finite positive number")
    quantum = Decimal("0.01") if price > 1 else Decimal("0.0001")
    rounding = ROUND_CEILING if side.strip().lower() == "buy" else ROUND_FLOOR
    return float(price.quantize(quantum, rounding=rounding))


def _positive_number(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise OrderContractError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise OrderContractError(f"{field} must be a finite positive number")
    return number


def validate_equity_order(raw: Dict[str, Any], *, require_idempotency: bool = False) -> ValidatedEquityOrder:
    symbol = str(raw.get("symbol") or raw.get("ticker") or "").strip().upper()
    if not symbol:
        raise OrderContractError("symbol is required")
    side = str(raw.get("side") or raw.get("action") or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise OrderContractError("side must be buy or sell")
    order_type = str(raw.get("order_type") or "market").strip().lower()
    if order_type not in {"market", "limit"}:
        raise OrderContractError("order_type must be market or limit")
    market_hours = str(raw.get("market_hours") or "regular_hours").strip().lower()
    if market_hours not in {"regular_hours", "extended_hours", "closed"}:
        raise OrderContractError("market_hours must be regular_hours, extended_hours, or closed")

    quantity_raw = raw.get("quantity")
    dollars_raw = raw.get("dollar_amount")
    if quantity_raw is not None and dollars_raw is not None:
        raise OrderContractError("provide quantity or dollar_amount, not both")
    if quantity_raw is None and dollars_raw is None:
        raise OrderContractError("quantity or dollar_amount is required")

    quantity = _positive_number(quantity_raw, "quantity") if quantity_raw is not None else None
    dollar_amount = _positive_number(dollars_raw, "dollar_amount") if dollars_raw is not None else None
    fractional = quantity is not None and not quantity.is_integer()
    amount_type = "dollar_amount" if dollar_amount is not None else (
        "fractional_shares" if fractional else "whole_shares"
    )

    limit_price = None
    if order_type == "limit":
        if dollar_amount is not None:
            raise OrderContractError("dollar_amount is valid only with market orders")
        if fractional:
            raise OrderContractError("limit order quantity cannot include fractional shares")
        limit_price = _positive_number(raw.get("limit_price", raw.get("price")), "limit_price")
        if limit_price > 1 and Decimal(str(limit_price)) % Decimal("0.01") != 0:
            raise OrderContractError("limit price above $1 must use whole-cent increments")

    if (fractional or dollar_amount is not None) and market_hours != "regular_hours":
        raise OrderContractError("fractional and dollar-based orders are regular-hours-only")
    if dollar_amount is not None and side != "buy":
        raise OrderContractError("dollar_amount is supported only for equity purchases")

    idempotency_key = raw.get("idempotency_key")
    if require_idempotency and not idempotency_key:
        raise OrderContractError("idempotency_key is required for placement")

    reference_price = raw.get("reference_price")
    if reference_price is not None:
        reference_price = _positive_number(reference_price, "reference_price")

    return ValidatedEquityOrder(
        symbol=symbol,
        side=side,
        order_type=order_type,
        amount_type=amount_type,
        market_hours=market_hours,
        quantity=quantity,
        dollar_amount=dollar_amount,
        limit_price=limit_price,
        reference_price=reference_price,
        idempotency_key=str(idempotency_key) if idempotency_key else None,
    )
