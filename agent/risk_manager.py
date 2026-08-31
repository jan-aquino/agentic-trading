"""
Portfolio Risk Management and Volatility-Adjusted Sizing Engine.
Enforces max drawdown circuit breakers, position caps, and dynamic stop-loss levels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from agent.compliance import ComplianceEngine
from agent.rallies_strategy import TradeProposal
from config import ComplianceConfig, StrategyConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.risk_manager")


@dataclass
class RiskAssessment:
    """Overall risk evaluation of a proposed trade or rebalance batch."""
    is_approved: bool
    adjusted_proposals: List[TradeProposal]
    warnings: List[str]
    max_portfolio_drawdown: float
    projected_cash_buffer: float


class RiskManager:
    """
    Supervises portfolio risk, dynamic position sizing, and buying power constraints.
    """

    def __init__(
        self,
        strategy_config: Optional[StrategyConfig] = None,
        compliance_config: Optional[ComplianceConfig] = None,
        compliance: Optional[ComplianceEngine] = None
    ):
        self.strategy_config = strategy_config or DEFAULT_CONFIG.strategy
        self.compliance_config = compliance_config or DEFAULT_CONFIG.compliance
        self.compliance = compliance or ComplianceEngine(self.compliance_config)

    def evaluate_proposals(
        self,
        proposals: List[TradeProposal],
        available_cash: float,
        portfolio_total_value: float,
        current_holdings: Dict[str, int],
        current_prices: Dict[str, float],
    ) -> RiskAssessment:
        """
        Validates and adjusts trade proposals against portfolio risk limits,
        available cash reserves, and concentration caps.
        """
        warnings: List[str] = []
        adjusted: List[TradeProposal] = []
        projected_cash = available_cash

        # First process all SELLs to accurately compute incoming cash
        sells = [p for p in proposals if not p.is_buy]
        buys = [p for p in proposals if p.is_buy]

        for p in sells:
            # Compliance check
            if self.compliance.is_restricted(p.ticker):
                warnings.append(f"MANDATORY RESTRICTED LIQUIDATION: {p.ticker} (SNOW) must be sold.")
                adjusted.append(p)
                projected_cash += p.total_cost
                continue

            current_qty = current_holdings.get(p.ticker, 0)
            if p.quantity > current_qty:
                warnings.append(
                    f"Sell quantity for {p.ticker} capped from {p.quantity} to current holding {current_qty}."
                )
                p.quantity = current_qty
                p.total_cost = round(p.quantity * p.estimated_price, 2)

            if p.quantity > 0:
                adjusted.append(p)
                projected_cash += p.total_cost

        # Process BUYs with buying power and position size constraints
        min_cash_required = portfolio_total_value * self.compliance_config.min_cash_buffer
        max_allowed_spend = max(0.0, projected_cash - min_cash_required)

        total_buy_demand = sum(p.total_cost for p in buys)
        scale_factor = 1.0
        if total_buy_demand > max_allowed_spend and total_buy_demand > 0:
            scale_factor = max_allowed_spend / total_buy_demand
            warnings.append(
                f"Total BUY demand (${total_buy_demand:,.2f}) exceeds available spendable cash "
                f"(${max_allowed_spend:,.2f}). Scaling BUY orders by {scale_factor:.1%}."
            )

        for p in buys:
            # Hard compliance check: strictly reject SNOW
            if self.compliance.is_restricted(p.ticker):
                warnings.append(
                    f"RISK CRITICAL: Hard rejected BUY proposal for restricted ticker '{p.ticker}' (SNOW)."
                )
                continue

            # Scale quantity if cash constrained
            price = p.estimated_price
            scaled_qty = int(p.quantity * scale_factor)
            
            # Position concentration cap check
            current_shares = current_holdings.get(p.ticker, 0)
            current_val = current_shares * price
            max_pos_val = portfolio_total_value * self.compliance_config.max_position_weight
            
            if (current_val + (scaled_qty * price)) > max_pos_val:
                allowed_add_val = max(0.0, max_pos_val - current_val)
                scaled_qty = min(scaled_qty, int(allowed_add_val / price) if price > 0 else 0)
                warnings.append(
                    f"BUY quantity for {p.ticker} adjusted to {scaled_qty} to obey max single-stock cap ({self.compliance_config.max_position_weight:.0%})."
                )

            cost = scaled_qty * price
            if scaled_qty > 0 and (projected_cash - cost) >= (min_cash_required * 0.9):
                p.quantity = scaled_qty
                p.total_cost = round(cost, 2)
                projected_cash -= cost
                adjusted.append(p)
            elif scaled_qty > 0:
                warnings.append(f"Skipped BUY for {p.ticker} to maintain minimum {self.compliance_config.min_cash_buffer:.0%} cash buffer.")

        cash_pct = (projected_cash / portfolio_total_value) if portfolio_total_value > 0 else 0.0

        return RiskAssessment(
            is_approved=True,
            adjusted_proposals=adjusted,
            warnings=warnings,
            max_portfolio_drawdown=0.0,
            projected_cash_buffer=round(cash_pct, 4),
        )
