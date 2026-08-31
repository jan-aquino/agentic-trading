"""
Compliance and Restriction Engine.
Enforces strict blacklists (e.g. Snowflake 'SNOW' exclusion for Snowflake employees),
maximum position limits, cash reserves, and portfolio risk bounds.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from config import ComplianceConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.compliance")


class ComplianceViolationError(Exception):
    """Raised when a restricted security or severe compliance constraint is violated."""
    pass


@dataclass
class ComplianceCheckResult:
    """Result of a compliance validation check."""
    is_compliant: bool
    ticker: str
    reasons: List[str]
    suggested_action: Optional[str] = None

    def __bool__(self) -> bool:
        return self.is_compliant


class ComplianceEngine:
    """
    Enforces compliance restrictions, specifically ticker blacklists (SNOW),
    maximum position concentration, and minimum cash reserve requirements.
    """

    def __init__(self, config: Optional[ComplianceConfig] = None):
        self.config = config or DEFAULT_CONFIG.compliance
        # Normalize restricted tickers to uppercase
        self._restricted_set: Set[str] = {
            t.strip().upper() for t in self.config.restricted_tickers if t.strip()
        }
        logger.info(f"Compliance engine initialized with restricted tickers: {self._restricted_set}")

    @property
    def restricted_tickers(self) -> Set[str]:
        return set(self._restricted_set)

    def is_restricted(self, ticker: str) -> bool:
        """Check whether a single ticker is restricted."""
        if not ticker:
            return False
        return ticker.strip().upper() in self._restricted_set

    def filter_universe(self, tickers: Iterable[str]) -> List[str]:
        """
        Filter a list of tickers, stripping any restricted symbols (e.g., SNOW).
        Logs warnings if restricted symbols are encountered.
        """
        approved: List[str] = []
        for t in tickers:
            clean = t.strip().upper()
            if self.is_restricted(clean):
                logger.warning(
                    f"COMPLIANCE ALERT: Excluded restricted ticker '{clean}' from universe."
                )
            else:
                approved.append(clean)
        return approved

    def sanitize_target_weights(
        self,
        weights: Dict[str, float],
        allow_cash_reallocation: bool = True
    ) -> Dict[str, float]:
        """
        Sanitizes a dictionary of target allocation weights:
        1. Strips any restricted ticker (e.g. SNOW) completely (weight set to 0.0).
        2. Redistributes the stripped weight across remaining non-cash assets proportionally,
           or assigns it to cash if no other assets exist.
        3. Enforces max single-position weight limits.
        4. Normalizes weights to sum to 1.0.
        """
        sanitized = {k.upper(): v for k, v in weights.items()}
        stripped_weight = 0.0

        for restricted in self._restricted_set:
            if restricted in sanitized and sanitized[restricted] > 0:
                stripped = sanitized.pop(restricted)
                stripped_weight += stripped
                logger.warning(
                    f"COMPLIANCE ENFORCED: Removed {restricted} target weight ({stripped:.2%})."
                )

        if not sanitized:
            return {"CASH": 1.0}

        # If we stripped restricted weights, reallocate to other stock assets
        if stripped_weight > 0:
            stock_keys = [k for k in sanitized if k != "CASH"]
            if stock_keys:
                current_stock_sum = sum(sanitized[k] for k in stock_keys)
                if current_stock_sum > 0:
                    for k in stock_keys:
                        sanitized[k] += stripped_weight * (sanitized[k] / current_stock_sum)
                else:
                    per_stock = stripped_weight / len(stock_keys)
                    for k in stock_keys:
                        sanitized[k] += per_stock
            else:
                sanitized["CASH"] = sanitized.get("CASH", 0.0) + stripped_weight

        # Cap single position weight to max_position_weight (e.g. 25%)
        max_weight = self.config.max_position_weight
        excess_sum = 0.0
        for k in list(sanitized.keys()):
            if k != "CASH" and sanitized[k] > max_weight:
                excess = sanitized[k] - max_weight
                sanitized[k] = max_weight
                excess_sum += excess

        if excess_sum > 0:
            sanitized["CASH"] = sanitized.get("CASH", 0.0) + excess_sum

        # Ensure cash meets minimum requirement
        min_cash = self.config.min_cash_buffer
        if sanitized.get("CASH", 0.0) < min_cash:
            deficit = min_cash - sanitized.get("CASH", 0.0)
            stock_keys = [k for k in sanitized if k != "CASH"]
            stock_sum = sum(sanitized[k] for k in stock_keys)
            if stock_sum > 0:
                for k in stock_keys:
                    sanitized[k] -= deficit * (sanitized[k] / stock_sum)
            sanitized["CASH"] = min_cash

        # Final normalization to ensure exact 1.0 sum
        total = sum(sanitized.values())
        if total > 0:
            sanitized = {k: round(v / total, 6) for k, v in sanitized.items()}

        return sanitized

    def validate_order(
        self,
        ticker: str,
        action: str,
        quantity: float,
        price: float,
        portfolio_value: float,
        current_holding_value: float = 0.0,
    ) -> ComplianceCheckResult:
        """
        Validates an individual order before routing to broker / MCP.
        Strictly blocks any BUY/SELL on restricted tickers (SNOW) or limit violations.
        """
        clean_ticker = ticker.strip().upper()
        reasons: List[str] = []

        # Check 1: Restricted ticker
        if self.is_restricted(clean_ticker):
            reasons.append(
                f"SECURITY RESTRICTION: '{clean_ticker}' is strictly blacklisted by compliance policy."
            )
            if self.config.enable_strict_mode:
                raise ComplianceViolationError(
                    f"Execution blocked: {clean_ticker} is restricted for trading."
                )
            return ComplianceCheckResult(
                is_compliant=False,
                ticker=clean_ticker,
                reasons=reasons,
                suggested_action="CANCEL_ORDER",
            )

        # Check 2: Position concentration limit on BUY
        clean_action = action.strip().upper()
        if clean_action == "BUY" and portfolio_value > 0:
            order_cost = quantity * price
            new_total_value = current_holding_value + order_cost
            new_weight = new_total_value / portfolio_value

            if new_weight > self.config.max_position_weight:
                reasons.append(
                    f"CONCENTRATION LIMIT: Order would result in {new_weight:.2%} allocation "
                    f"exceeding maximum permitted {self.config.max_position_weight:.2%}."
                )
                max_allowed_cost = max(0.0, (self.config.max_position_weight * portfolio_value) - current_holding_value)
                max_allowed_qty = int(max_allowed_cost / price) if price > 0 else 0
                return ComplianceCheckResult(
                    is_compliant=False,
                    ticker=clean_ticker,
                    reasons=reasons,
                    suggested_action=f"REDUCE_QUANTITY_TO_{max_allowed_qty}",
                )

        return ComplianceCheckResult(
            is_compliant=True,
            ticker=clean_ticker,
            reasons=["PASSED_ALL_COMPLIANCE_CHECKS"],
        )
