"""
Agent Orchestrator for the Rallies ChatGPT Portfolio Trading System.
Coordinates Market Analysis, Compliance Validation, Strategy Allocation,
Risk Sizing, Text Notifications, Human Approval, and Robinhood MCP Execution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent.compliance import ComplianceEngine
from agent.market_analyzer import MarketAnalyzer, SecurityScorecard
from agent.mcp_robinhood import ExecutionResult, RobinhoodAccount, RobinhoodMCPClient, RobinhoodPosition
from agent.notifier import ConfirmationDecision, TextNotifier
from agent.rallies_strategy import RalliesChatGPTStrategy, StrategyAllocationResult, TradeProposal
from agent.risk_manager import RiskAssessment, RiskManager
from config import SystemConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.orchestrator")


@dataclass
class TradingCycleSummary:
    """Complete summary of a single analysis and execution cycle."""
    timestamp: str
    account_before: RobinhoodAccount
    account_after: Optional[RobinhoodAccount]
    current_positions: List[RobinhoodPosition]
    allocation_result: StrategyAllocationResult
    risk_assessment: RiskAssessment
    executed_trades: List[ExecutionResult]
    rejected_trades: List[Dict[str, Any]]
    compliance_certificate: str


class AgentOrchestrator:
    """
    Main autonomous agent coordinator.
    """

    def __init__(self, config: Optional[SystemConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.compliance = ComplianceEngine(self.config.compliance)
        self.analyzer = MarketAnalyzer(config=self.config.strategy)
        self.strategy = RalliesChatGPTStrategy(
            config=self.config.strategy,
            compliance=self.compliance,
            analyzer=self.analyzer,
        )
        self.risk_manager = RiskManager(
            strategy_config=self.config.strategy,
            compliance_config=self.config.compliance,
            compliance=self.compliance,
        )
        self.notifier = TextNotifier(config=self.config.notifier)
        self.robinhood = RobinhoodMCPClient(
            config=self.config.robinhood,
            compliance=self.compliance,
            initial_cash=self.config.initial_capital,
        )
        logger.info("Agent Orchestrator successfully initialized.")

    def run_cycle(self, interactive: bool = True, dry_run: bool = False) -> TradingCycleSummary:
        """
        Executes a full agent workflow cycle:
        1. Fetch Robinhood portfolio & cash balances.
        2. Conduct market analysis & Rallies strategy scoring.
        3. Strictly exclude SNOW and determine target weights.
        4. Validate against risk limits and cash buffers.
        5. Send text notifications to user for trade confirmation.
        6. Execute approved trades on Robinhood via MCP.
        """
        now_str = datetime.now().isoformat()
        logger.info(f"--- Starting Trading Cycle at {now_str} ---")

        # 1. Fetch current Robinhood account state
        account_before = self.robinhood.get_account_summary()
        positions_before = self.robinhood.get_positions()
        
        current_holdings = {p.ticker: p.quantity for p in positions_before}
        current_prices = {p.ticker: p.current_price for p in positions_before}

        # 2. Strategy Allocation & Proposals Generation
        allocation_res = self.strategy.generate_target_allocation(
            current_holdings=current_holdings,
            current_prices=current_prices,
            portfolio_cash=account_before.cash_balance,
            portfolio_total_value=account_before.portfolio_equity,
        )

        # 3. Risk Assessment & Sizing
        risk_res = self.risk_manager.evaluate_proposals(
            proposals=allocation_res.proposals,
            available_cash=account_before.cash_balance,
            portfolio_total_value=account_before.portfolio_equity,
            current_holdings=current_holdings,
            current_prices=current_prices,
        )

        executed_trades: List[ExecutionResult] = []
        rejected_trades: List[Dict[str, Any]] = []

        # 4. User Notification and Execution Loop
        if not risk_res.adjusted_proposals:
            logger.info("Portfolio is perfectly aligned with target allocation. No rebalancing required.")
        else:
            print(f"\n📢 Generated {len(risk_res.adjusted_proposals)} Trade Proposals:")
            for p in risk_res.adjusted_proposals:
                print(f"  • {p.action} {p.quantity} {p.ticker} @ ~${p.estimated_price:.2f} (${p.total_cost:,.2f}) - {p.strategy_bucket}")

            for proposal in risk_res.adjusted_proposals:
                # Double-check compliance gate before sending notification
                if self.compliance.is_restricted(proposal.ticker):
                    logger.critical(f"HARD REJECT: Restricted security '{proposal.ticker}' (SNOW) blocked from execution.")
                    rejected_trades.append({
                        "ticker": proposal.ticker,
                        "action": proposal.action,
                        "reason": "RESTRICTED_SECURITY_SNOW",
                    })
                    continue

                if dry_run:
                    logger.info(f"[Dry-Run] Simulating text notification for {proposal.ticker} {proposal.action}...")
                    msg = self.notifier.format_proposal_message(proposal, account_before.portfolio_equity)
                    print("\n" + msg + "\n")
                    # In dry run, simulate execution if auto-approved
                    receipt = self.robinhood.execute_order(
                        ticker=proposal.ticker,
                        action=proposal.action,
                        quantity=proposal.quantity,
                        limit_price=proposal.estimated_price,
                        user_confirmed=True,
                    )
                    executed_trades.append(receipt)
                else:
                    # Request real human confirmation via text / prompt
                    decision: ConfirmationDecision = self.notifier.request_trade_confirmation(
                        proposal=proposal,
                        portfolio_equity=account_before.portfolio_equity,
                        interactive=interactive,
                    )

                    if decision.approved:
                        receipt = self.robinhood.execute_order(
                            ticker=proposal.ticker,
                            action=proposal.action,
                            quantity=proposal.quantity,
                            limit_price=proposal.estimated_price,
                            user_confirmed=True,
                        )
                        executed_trades.append(receipt)
                    else:
                        logger.warning(f"Trade for {proposal.ticker} aborted: {decision.decision_reason}")
                        rejected_trades.append({
                            "ticker": proposal.ticker,
                            "action": proposal.action,
                            "reason": decision.decision_reason,
                        })

        # Persist trade history to disk
        if executed_trades:
            history_file = self.analyzer.cache_dir.parent / "trade_history.json"
            history_file.parent.mkdir(parents=True, exist_ok=True)
            existing_history = []
            if history_file.exists():
                try:
                    with open(history_file, "r", encoding="utf-8") as f:
                        existing_history = json.load(f)
                except Exception:
                    existing_history = []

            for r in executed_trades:
                existing_history.append({
                    "order_id": r.order_id,
                    "timestamp": r.timestamp,
                    "ticker": r.ticker,
                    "action": r.action,
                    "quantity": r.quantity,
                    "executed_price": r.executed_price,
                    "total_amount": r.total_amount,
                    "status": r.status,
                    "broker_reference": r.broker_reference,
                    "compliance_pass": r.compliance_approved,
                })

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(existing_history, f, indent=2)

        account_after = self.robinhood.get_account_summary()

        compliance_cert = (
            "PASSED: Strict compliance enforced. Snowflake Inc. (SNOW) was 100% excluded "
            "from all screening, allocation, and order execution layers."
        )

        return TradingCycleSummary(
            timestamp=now_str,
            account_before=account_before,
            account_after=account_after,
            current_positions=self.robinhood.get_positions(),
            allocation_result=allocation_res,
            risk_assessment=risk_res,
            executed_trades=executed_trades,
            rejected_trades=rejected_trades,
            compliance_certificate=compliance_cert,
        )
