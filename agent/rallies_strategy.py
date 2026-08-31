"""
Rallies ChatGPT Portfolio Emulation Strategy.
Implements the multi-asset AI infrastructure + core defensive anchor strategy
with dynamic momentum rebalancing, cash buffering, and strict SNOW exclusion.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agent.compliance import ComplianceEngine
from agent.market_analyzer import MarketAnalyzer, SecurityScorecard
from config import StrategyConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.rallies_strategy")


@dataclass
class TradeProposal:
    """A proposed rebalancing trade awaiting user confirmation."""
    ticker: str
    action: str          # 'BUY' or 'SELL'
    quantity: int        # Number of shares
    estimated_price: float
    total_cost: float
    current_weight: float
    target_weight: float
    weight_delta: float
    strategy_bucket: str # 'AI_INFRASTRUCTURE' or 'CORE_DIVERSIFIED'
    thesis: str
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def is_buy(self) -> bool:
        return self.action.upper() == "BUY"


@dataclass
class StrategyAllocationResult:
    """Summary of target portfolio allocation and generated trade proposals."""
    timestamp: str
    scorecards: Dict[str, SecurityScorecard]
    target_weights: Dict[str, float]
    proposals: List[TradeProposal]
    ai_infra_total_weight: float
    core_diversified_total_weight: float
    cash_weight: float
    compliance_status: str


class RalliesChatGPTStrategy:
    """
    Emulates the ChatGPT Portfolio from the Rallies AI Arena:
    - High-conviction AI infrastructure picks (Credo, Nebius, Alphabet, Nvidia, Amphenol, etc.)
    - Resilient diversifiers (JPMorgan, Progressive, Visa, Cigna, Leidos)
    - Dynamic risk-managed rebalancing with cash reserves (10-15%)
    - Strict compliance filtering (zero SNOW exposure)
    """

    def __init__(
        self,
        config: Optional[StrategyConfig] = None,
        compliance: Optional[ComplianceEngine] = None,
        analyzer: Optional[MarketAnalyzer] = None
    ):
        self.config = config or DEFAULT_CONFIG.strategy
        self.compliance = compliance or ComplianceEngine()
        self.analyzer = analyzer or MarketAnalyzer(config=self.config)

    def generate_target_allocation(
        self,
        current_holdings: Dict[str, int],
        current_prices: Dict[str, float],
        portfolio_cash: float,
        portfolio_total_value: float,
        max_ai_picks: int = 5,
        max_core_picks: int = 3,
    ) -> StrategyAllocationResult:
        """
        Calculates optimal target allocation weights and trade proposals.
        """
        # Step 1: Filter universes through compliance (strictly strips SNOW)
        ai_candidates = self.compliance.filter_universe(self.config.ai_infra_universe)
        core_candidates = self.compliance.filter_universe(self.config.core_diversified_universe)

        scorecards: Dict[str, SecurityScorecard] = {}

        # Evaluate AI Infrastructure candidate basket
        for ticker in ai_candidates:
            try:
                card = self.analyzer.evaluate_security(ticker, category="AI_INFRA")
                scorecards[ticker] = card
            except Exception as e:
                logger.error(f"Error scoring {ticker}: {e}")

        # Evaluate Core Diversified candidate basket
        for ticker in core_candidates:
            try:
                card = self.analyzer.evaluate_security(ticker, category="CORE_DIVERSIFIED")
                scorecards[ticker] = card
            except Exception as e:
                logger.error(f"Error scoring {ticker}: {e}")

        # Step 2: Rank and select top performers in each basket
        ai_ranked = sorted(
            [c for c in scorecards.values() if c.category == "AI_INFRA"],
            key=lambda x: x.composite_rank,
            reverse=True
        )
        core_ranked = sorted(
            [c for c in scorecards.values() if c.category == "CORE_DIVERSIFIED"],
            key=lambda x: x.composite_rank,
            reverse=True
        )

        selected_ai = [c for c in ai_ranked if c.signal in ("STRONG_BUY", "BUY", "HOLD")][:max_ai_picks]
        selected_core = [c for c in core_ranked if c.signal in ("STRONG_BUY", "BUY", "HOLD")][:max_core_picks]

        # Fallback if market conditions are weak
        if not selected_ai and ai_ranked:
            selected_ai = ai_ranked[:3]
        if not selected_core and core_ranked:
            selected_core = core_ranked[:2]

        raw_weights: Dict[str, float] = {}

        # Distribute AI infrastructure budget (e.g. 65%) based on composite scores
        ai_budget = self.config.ai_infra_target_weight
        if selected_ai:
            total_ai_score = sum(c.composite_rank for c in selected_ai)
            for c in selected_ai:
                raw_weights[c.ticker] = ai_budget * (c.composite_rank / total_ai_score)

        # Distribute Core diversified budget (e.g. 23%)
        core_budget = self.config.core_diversified_target_weight
        if selected_core:
            total_core_score = sum(c.composite_rank for c in selected_core)
            for c in selected_core:
                raw_weights[c.ticker] = core_budget * (c.composite_rank / total_core_score)

        # Cash buffer allocation
        raw_weights["CASH"] = self.config.cash_target_weight

        # Step 3: Sanitize target weights via Compliance Engine (guarantees SNOW is 0.0 and weights are capped)
        sanitized_weights = self.compliance.sanitize_target_weights(raw_weights)

        # Step 4: Generate concrete trade proposals
        proposals: List[TradeProposal] = []
        current_weights: Dict[str, float] = {}

        # Calculate current weights
        for ticker, qty in current_holdings.items():
            t_upper = ticker.upper()
            price = current_prices.get(t_upper, 0.0)
            if price == 0.0 and t_upper in scorecards:
                price = scorecards[t_upper].last_price
            val = qty * price
            current_weights[t_upper] = (val / portfolio_total_value) if portfolio_total_value > 0 else 0.0

        all_tickers = set(sanitized_weights.keys()).union(current_weights.keys())
        all_tickers.discard("CASH")

        # First pass: Generate SELL proposals (to raise cash if trimming/exiting)
        for ticker in sorted(all_tickers):
            # Check compliance rule
            if self.compliance.is_restricted(ticker):
                # If holding restricted ticker, must liquidate immediately
                qty = current_holdings.get(ticker, 0)
                if qty > 0:
                    price = current_prices.get(ticker, scorecards.get(ticker, None).last_price if ticker in scorecards else 100.0)
                    proposals.append(TradeProposal(
                        ticker=ticker,
                        action="SELL",
                        quantity=qty,
                        estimated_price=round(price, 2),
                        total_cost=round(qty * price, 2),
                        current_weight=current_weights.get(ticker, 0.0),
                        target_weight=0.0,
                        weight_delta=-current_weights.get(ticker, 0.0),
                        strategy_bucket="RESTRICTED_LIQUIDATION",
                        thesis="MANDATORY COMPLIANCE EXIT: restricted security (SNOW) detected.",
                        stop_loss=0.0,
                        take_profit=0.0,
                        risk_reward_ratio=0.0,
                    ))
                continue

            c_weight = current_weights.get(ticker, 0.0)
            t_weight = sanitized_weights.get(ticker, 0.0)
            weight_diff = t_weight - c_weight
            price = current_prices.get(ticker, scorecards.get(ticker, None).last_price if ticker in scorecards else 0.0)
            if price <= 0:
                continue

            card = scorecards.get(ticker)
            bucket = "AI_INFRASTRUCTURE" if (card and card.category == "AI_INFRA") else "CORE_DIVERSIFIED"

            # If target weight is significantly lower than current weight (> 1.5% drift)
            if weight_diff < -0.015:
                dollar_diff = abs(weight_diff) * portfolio_total_value
                shares_to_sell = int(dollar_diff / price)
                current_qty = current_holdings.get(ticker, 0)
                shares_to_sell = min(shares_to_sell, current_qty)

                if shares_to_sell > 0:
                    stop_loss = card.target_stop_loss if card else round(price * 0.92, 2)
                    take_profit = card.target_take_profit if card else round(price * 1.20, 2)
                    thesis = (
                        f"Rebalance Trim: Current allocation ({c_weight:.1%}) exceeds target ({t_weight:.1%}). "
                        f"Locking in gains and reallocating."
                    )
                    proposals.append(TradeProposal(
                        ticker=ticker,
                        action="SELL",
                        quantity=shares_to_sell,
                        estimated_price=round(price, 2),
                        total_cost=round(shares_to_sell * price, 2),
                        current_weight=round(c_weight, 4),
                        target_weight=round(t_weight, 4),
                        weight_delta=round(weight_diff, 4),
                        strategy_bucket=bucket,
                        thesis=thesis,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        risk_reward_ratio=2.5,
                    ))

        # Second pass: Generate BUY proposals
        for ticker in sorted(all_tickers):
            if self.compliance.is_restricted(ticker):
                continue

            c_weight = current_weights.get(ticker, 0.0)
            t_weight = sanitized_weights.get(ticker, 0.0)
            weight_diff = t_weight - c_weight
            price = current_prices.get(ticker, scorecards.get(ticker, None).last_price if ticker in scorecards else 0.0)
            if price <= 0:
                continue

            card = scorecards.get(ticker)
            bucket = "AI_INFRASTRUCTURE" if (card and card.category == "AI_INFRA") else "CORE_DIVERSIFIED"

            # If target weight is significantly higher (> 1.5% drift)
            if weight_diff > 0.015:
                dollar_diff = weight_diff * portfolio_total_value
                shares_to_buy = int(dollar_diff / price)

                if shares_to_buy > 0:
                    stop_loss = card.target_stop_loss if card else round(price * 0.92, 2)
                    take_profit = card.target_take_profit if card else round(price * 1.25, 2)
                    rr_ratio = round((take_profit - price) / max(0.01, price - stop_loss), 2)
                    reasons_str = "; ".join(card.signal_reasons) if card else "Target basket allocation"
                    thesis = (
                        f"Target Allocation ({t_weight:.1%}): Momentum composite {card.composite_rank if card else 0:.1f}. "
                        f"{reasons_str}"
                    )
                    proposals.append(TradeProposal(
                        ticker=ticker,
                        action="BUY",
                        quantity=shares_to_buy,
                        estimated_price=round(price, 2),
                        total_cost=round(shares_to_buy * price, 2),
                        current_weight=round(c_weight, 4),
                        target_weight=round(t_weight, 4),
                        weight_delta=round(weight_diff, 4),
                        strategy_bucket=bucket,
                        thesis=thesis,
                        stop_loss=stop_loss,
                        take_profit=take_profit,
                        risk_reward_ratio=rr_ratio,
                    ))

        # Calculate category weight totals
        ai_total_wt = sum(sanitized_weights.get(t, 0.0) for t in ai_candidates)
        core_total_wt = sum(sanitized_weights.get(t, 0.0) for t in core_candidates)
        cash_wt = sanitized_weights.get("CASH", self.config.cash_target_weight)

        return StrategyAllocationResult(
            timestamp=datetime.now().isoformat(),
            scorecards=scorecards,
            target_weights=sanitized_weights,
            proposals=proposals,
            ai_infra_total_weight=round(ai_total_wt, 4),
            core_diversified_total_weight=round(core_total_wt, 4),
            cash_weight=round(cash_wt, 4),
            compliance_status="PASSED (SNOW strictly excluded)",
        )
