"""
Robinhood MCP (Model Context Protocol) Integration and Order Routing Engine.
Connects to Robinhood MCP server tools for account status, positions,
and order execution with immutable compliance validation (strictly blocking SNOW).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from agent.compliance import ComplianceCheckResult, ComplianceEngine, ComplianceViolationError
from config import RobinhoodMCPConfig, DEFAULT_CONFIG

logger = logging.getLogger("agent.mcp_robinhood")


class LiveBrokerUnavailableError(RuntimeError):
    """Raised when standalone Python attempts a live Robinhood action.

    Robinhood's supported integration is an authenticated MCP connection owned
    by the host agent (Codex), not a username/password API for this process.
    """


@dataclass
class RobinhoodAccount:
    """Robinhood account summary."""
    account_number: str
    buying_power: float
    cash_balance: float
    portfolio_equity: float
    unsettled_funds: float
    is_day_trader: bool = False
    currency: str = "USD"


@dataclass
class RobinhoodPosition:
    """An open position in Robinhood."""
    ticker: str
    quantity: int
    average_buy_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


@dataclass
class OrderPreview:
    """Estimated fill details before execution."""
    ticker: str
    action: str
    quantity: int
    estimated_price: float
    estimated_total: float
    estimated_slippage_bps: float
    estimated_sec_fee: float
    compliance_check: ComplianceCheckResult


@dataclass
class ExecutionResult:
    """Trade execution receipt."""
    order_id: str
    ticker: str
    action: str
    quantity: int
    executed_price: float
    total_amount: float
    status: str  # 'FILLED', 'REJECTED', 'PENDING', 'CANCELLED'
    timestamp: str
    compliance_approved: bool
    rejection_reason: Optional[str] = None
    broker_reference: Optional[str] = None


class RobinhoodMCPClient:
    """
    Client for Robinhood MCP Server.
    Provides safe tool calling for Robinhood brokerage operations with dry-run/mock fallback.
    """

    def __init__(
        self,
        config: Optional[RobinhoodMCPConfig] = None,
        compliance: Optional[ComplianceEngine] = None,
        initial_cash: float = 100000.0,
    ):
        self.config = config or DEFAULT_CONFIG.robinhood
        self.compliance = compliance or ComplianceEngine()
        self.use_mock = self.config.use_mock

        # Internal state for mock/dry-run mode
        self._mock_cash = initial_cash
        self._mock_positions: Dict[str, Dict[str, Any]] = {}
        self._mock_orders: Dict[str, ExecutionResult] = {}
        logger.info(f"Robinhood MCP Client initialized (Mock Mode: {self.use_mock})")

    def get_account_summary(self) -> RobinhoodAccount:
        """Retrieves Robinhood account balances and buying power."""
        if self.use_mock:
            pos_val = sum(
                p["quantity"] * p["current_price"] for p in self._mock_positions.values()
            )
            total_equity = self._mock_cash + pos_val
            return RobinhoodAccount(
                account_number="RH-MOCK-7829104",
                buying_power=round(self._mock_cash, 2),
                cash_balance=round(self._mock_cash, 2),
                portfolio_equity=round(total_equity, 2),
                unsettled_funds=0.0,
            )

        # Live MCP tool dispatch
        result = self._call_mcp_tool("robinhood_get_account", {})
        return RobinhoodAccount(
            account_number=result.get("account_number", "RH-LIVE"),
            buying_power=float(result.get("buying_power", 0.0)),
            cash_balance=float(result.get("cash", 0.0)),
            portfolio_equity=float(result.get("equity", 0.0)),
            unsettled_funds=float(result.get("unsettled_funds", 0.0)),
        )

    def get_positions(self) -> List[RobinhoodPosition]:
        """Retrieves currently open positions."""
        if self.use_mock:
            positions: List[RobinhoodPosition] = []
            for ticker, data in self._mock_positions.items():
                if data["quantity"] > 0:
                    mkt_val = data["quantity"] * data["current_price"]
                    cost_basis = data["quantity"] * data["avg_price"]
                    pnl = mkt_val - cost_basis
                    pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0.0
                    positions.append(RobinhoodPosition(
                        ticker=ticker,
                        quantity=data["quantity"],
                        average_buy_price=round(data["avg_price"], 2),
                        current_price=round(data["current_price"], 2),
                        market_value=round(mkt_val, 2),
                        unrealized_pnl=round(pnl, 2),
                        unrealized_pnl_pct=round(pnl_pct, 2),
                    ))
            return positions

        # Live MCP tool dispatch
        raw_positions = self._call_mcp_tool("robinhood_get_positions", {})
        positions = []
        for p in raw_positions.get("positions", []):
            positions.append(RobinhoodPosition(
                ticker=p["ticker"],
                quantity=int(p["quantity"]),
                average_buy_price=float(p["average_buy_price"]),
                current_price=float(p["current_price"]),
                market_value=float(p["market_value"]),
                unrealized_pnl=float(p.get("unrealized_pnl", 0.0)),
                unrealized_pnl_pct=float(p.get("unrealized_pnl_pct", 0.0)),
            ))
        return positions

    def preview_order(
        self,
        ticker: str,
        action: str,
        quantity: int,
        estimated_price: float
    ) -> OrderPreview:
        """
        Calculates estimated costs, slippage, and runs pre-trade compliance checks.
        """
        clean_ticker = ticker.strip().upper()
        clean_action = action.strip().upper()

        account = self.get_account_summary()
        cur_pos_val = 0.0
        for p in self.get_positions():
            if p.ticker == clean_ticker:
                cur_pos_val = p.market_value

        # Run compliance check
        try:
            comp_check = self.compliance.validate_order(
                ticker=clean_ticker,
                action=clean_action,
                quantity=quantity,
                price=estimated_price,
                portfolio_value=account.portfolio_equity,
                current_holding_value=cur_pos_val,
            )
        except ComplianceViolationError as e:
            comp_check = ComplianceCheckResult(
                is_compliant=False,
                ticker=clean_ticker,
                reasons=[str(e)],
                suggested_action="CANCEL_ORDER",
            )

        # Slippage and fees
        slip_rate = self.config.slippage_bps / 10000.0
        fill_price = estimated_price * (1 + slip_rate if clean_action == "BUY" else 1 - slip_rate)
        est_total = quantity * fill_price
        sec_fee = (est_total * self.config.est_sec_fee_rate) if clean_action == "SELL" else 0.0

        return OrderPreview(
            ticker=clean_ticker,
            action=clean_action,
            quantity=quantity,
            estimated_price=round(fill_price, 2),
            estimated_total=round(est_total + sec_fee if clean_action == "BUY" else est_total - sec_fee, 2),
            estimated_slippage_bps=self.config.slippage_bps,
            estimated_sec_fee=round(sec_fee, 4),
            compliance_check=comp_check,
        )

    def execute_order(
        self,
        ticker: str,
        action: str,
        quantity: int,
        limit_price: Optional[float] = None,
        user_confirmed: bool = False,
    ) -> ExecutionResult:
        """
        Executes order on Robinhood via MCP tool.
        STRICT REQUIREMENT: User must have confirmed the trade, and SNOW is strictly blocked.
        """
        clean_ticker = ticker.strip().upper()
        clean_action = action.strip().upper()
        order_id = f"RH-ORD-{uuid.uuid4().hex[:8].upper()}"
        now_str = datetime.now().isoformat()

        # Failsafe 1: Human confirmation check
        if not user_confirmed:
            logger.error("TRADE REJECTED: User confirmation was not provided before execution attempt.")
            return ExecutionResult(
                order_id=order_id,
                ticker=clean_ticker,
                action=clean_action,
                quantity=quantity,
                executed_price=0.0,
                total_amount=0.0,
                status="REJECTED",
                timestamp=now_str,
                compliance_approved=False,
                rejection_reason="HUMAN_CONFIRMATION_REQUIRED: Trade was not confirmed by user.",
            )

        # Failsafe 2: Compliance engine restriction check (SNOW)
        if self.compliance.is_restricted(clean_ticker):
            logger.critical(f"COMPLIANCE BREACH BLOCKED: Refusing to route order for restricted ticker '{clean_ticker}'.")
            return ExecutionResult(
                order_id=order_id,
                ticker=clean_ticker,
                action=clean_action,
                quantity=quantity,
                executed_price=0.0,
                total_amount=0.0,
                status="REJECTED",
                timestamp=now_str,
                compliance_approved=False,
                rejection_reason=f"COMPLIANCE RESTRICTION: '{clean_ticker}' (Snowflake) is strictly prohibited.",
            )

        if self.use_mock:
            # Simulate execution in mock environment
            price = limit_price or 100.0
            slip_rate = self.config.slippage_bps / 10000.0
            fill_price = round(price * (1 + slip_rate if clean_action == "BUY" else 1 - slip_rate), 2)
            total_val = round(quantity * fill_price, 2)

            if clean_action == "BUY":
                if total_val > self._mock_cash:
                    return ExecutionResult(
                        order_id=order_id,
                        ticker=clean_ticker,
                        action=clean_action,
                        quantity=quantity,
                        executed_price=0.0,
                        total_amount=0.0,
                        status="REJECTED",
                        timestamp=now_str,
                        compliance_approved=True,
                        rejection_reason=f"INSUFFICIENT_BUYING_POWER: Need ${total_val:,.2f}, have ${self._mock_cash:,.2f}",
                    )
                self._mock_cash -= total_val
                if clean_ticker in self._mock_positions:
                    pos = self._mock_positions[clean_ticker]
                    new_qty = pos["quantity"] + quantity
                    new_avg = ((pos["quantity"] * pos["avg_price"]) + total_val) / new_qty
                    pos["quantity"] = new_qty
                    pos["avg_price"] = new_avg
                    pos["current_price"] = fill_price
                else:
                    self._mock_positions[clean_ticker] = {
                        "quantity": quantity,
                        "avg_price": fill_price,
                        "current_price": fill_price,
                    }
            elif clean_action == "SELL":
                current_qty = self._mock_positions.get(clean_ticker, {}).get("quantity", 0)
                if quantity > current_qty:
                    return ExecutionResult(
                        order_id=order_id,
                        ticker=clean_ticker,
                        action=clean_action,
                        quantity=quantity,
                        executed_price=0.0,
                        total_amount=0.0,
                        status="REJECTED",
                        timestamp=now_str,
                        compliance_approved=True,
                        rejection_reason=f"INSUFFICIENT_SHARES: Attempted to sell {quantity}, holding {current_qty}.",
                    )
                self._mock_cash += total_val
                self._mock_positions[clean_ticker]["quantity"] -= quantity
                if self._mock_positions[clean_ticker]["quantity"] == 0:
                    del self._mock_positions[clean_ticker]

            receipt = ExecutionResult(
                order_id=order_id,
                ticker=clean_ticker,
                action=clean_action,
                quantity=quantity,
                executed_price=fill_price,
                total_amount=total_val,
                status="FILLED",
                timestamp=now_str,
                compliance_approved=True,
                broker_reference="MOCK-ROBINHOOD-FILL",
            )
            self._mock_orders[order_id] = receipt
            logger.info(f"Order executed successfully in Robinhood MCP Mock: {receipt}")
            return receipt

        # Live MCP Tool / Broker execution
        tool_args = {
            "symbol": clean_ticker,
            "action": clean_action.lower(),
            "quantity": quantity,
            "order_type": "limit" if limit_price else "market",
            "price": limit_price,
        }
        res = self._call_mcp_tool("robinhood_place_order", tool_args)
        exec_price = float(res.get("executed_price", limit_price or 0.0))
        tot_val = float(res.get("total_amount", quantity * exec_price))
        return ExecutionResult(
            order_id=order_id,
            ticker=clean_ticker,
            action=clean_action,
            quantity=quantity,
            executed_price=exec_price,
            total_amount=tot_val,
            status=res.get("status", "FILLED"),
            timestamp=now_str,
            compliance_approved=True,
            broker_reference=res.get("broker_order_id", "RH-LIVE-FILL"),
        )

    def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Refuse standalone live broker calls.

        The former implementation used reverse-engineered ``robin_stocks``
        endpoints and then returned a synthetic success response if the broker
        call failed. That can cause the local audit trail to say a trade was
        filled when no broker order exists. The official Robinhood Trading MCP
        is authenticated in Codex and must be invoked there after this project's
        strategy/risk checks have produced a proposal.
        """
        logger.error("Blocked standalone live Robinhood call %s", tool_name)
        raise LiveBrokerUnavailableError(
            "Live Robinhood calls are disabled in this standalone process. "
            "Use the authenticated official Robinhood Trading MCP in Codex "
            "(get_accounts/get_portfolio/get_equity_positions/review_equity_order/place_equity_order)."
        )
