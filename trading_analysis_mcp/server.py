"""FastMCP entry point for ChatGPT Work's proposal-only trading tools."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agent.trading_analysis_service import TradingAnalysisService

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised by deployment smoke test
    raise RuntimeError(
        "The MCP SDK is not installed. Run: pip install -r requirements.txt"
    ) from exc


service = TradingAnalysisService()
mcp = FastMCP(
    "Trading Analysis",
    instructions=(
        "Proposal-only research and portfolio service. It never calls a broker or executes orders. "
        "Discover candidates dynamically with a research provider such as Rallies, gather evidence "
        "and fresh Robinhood data, then submit "
        "structured research packets. Plans are immutable and expiration is a hard blocker. Revalidate a plan "
        "immediately before asking for approval and using the separate Robinhood Trading MCP."
    ),
    stateless_http=True,
    json_response=True,
    host=os.getenv("HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8000")),
)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def get_strategy_policy() -> Dict[str, Any]:
    """Return enforced strategy, compliance, freshness, and execution-boundary policy."""
    return service.get_strategy_policy()


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def get_research_requirements() -> Dict[str, Any]:
    """Return the candidate research schema and evidence requirements.

    Call this before discovery. ChatGPT Work may use Rallies or another research
    provider to assemble candidates, while Robinhood remains authoritative for
    account, tradability, and executable-price fields.
    """
    return service.get_research_requirements()


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
def generate_trade_plan(
    account: Dict[str, Any],
    positions: List[Dict[str, Any]],
    research_candidates: List[Dict[str, Any]],
    market_data_as_of: str,
    market_session: str,
    mandate: Dict[str, Any] | None = None,
    planning_mode: str = "immediate",
) -> Dict[str, Any]:
    """Create an expiring, mandate-driven plan from researched dynamic candidates.

    This only produces order intents. It cannot review or place brokerage orders.
    Research every current holding as well as new candidates. Candidate packets
    must satisfy get_research_requirements. Pass the observed market_session.
    Immediate mode is rejected outside regular_hours. Use
    planning_mode=next_market_open after hours; that mode accepts recent closing prices, filters candidates
    above the volatility ceiling, and still requires fresh validation at open.
    """
    return service.generate_trade_plan(
        account, positions, research_candidates, market_data_as_of, mandate, planning_mode, market_session
    )


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def get_trade_plan(plan_id: str) -> Dict[str, Any]:
    """Retrieve an immutable plan by its opaque plan ID for review or audit."""
    return service.get_trade_plan(plan_id)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def validate_trade_plan(
    plan_id: str,
    account: Dict[str, Any],
    positions: List[Dict[str, Any]],
    quotes: List[Dict[str, Any]],
    market_data_as_of: str,
    market_session: str = "regular_hours",
) -> Dict[str, Any]:
    """Revalidate a plan against fresh Robinhood state and quotes.

    A successful result authorizes only the next review step; it is not user
    approval and does not call Robinhood. Fractional and dollar-based orders
    require market_session=regular_hours. If any blocker is returned, do not trade.
    """
    return service.validate_trade_plan(
        plan_id, account, positions, quotes, market_data_as_of, market_session
    )


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
