"""FastMCP entry point for the simplified V2 workflow."""

from __future__ import annotations

import os
from typing import Any, Dict, List

from agent.simple_value_service import SimpleValueService

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from exc


service = SimpleValueService()
mcp = FastMCP(
    "Simple Value Trading Analysis",
    instructions=(
        "V2 proposal-only workflow. ChatGPT Work performs web research and submits sourced facts. "
        "This MCP shortlists profitable low-P/E companies, proposes at most one purchase, and "
        "evaluates holdings for earnings-driven sell review. It never calls a broker."
    ),
    stateless_http=True,
    json_response=True,
    host=os.getenv("HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8000")),
)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def get_simple_policy() -> Dict[str, Any]:
    """Return the complete V2 screening, sizing, and sell-review policy."""
    return service.get_policy()


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def get_simple_research_requirements() -> Dict[str, Any]:
    """Return the exact web-research fields and source requirements."""
    return service.get_research_requirements()


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def shortlist_value_stocks(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Rank up to five profitable stocks with positive EPS and P/E no greater than 25."""
    return service.shortlist(candidates)


@mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False})
def propose_purchase(
    account: Dict[str, Any], positions: List[Dict[str, Any]], candidates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Create at most one buy proposal after accounting for holdings and spendable cash."""
    return service.propose_purchase(account, positions, candidates)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def evaluate_holdings(holding_research: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify researched holdings as HOLD, WATCH, or SELL_REVIEW."""
    return service.evaluate_holdings(holding_research)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def get_simple_plan(plan_id: str) -> Dict[str, Any]:
    """Retrieve an immutable V2 proposal for review or audit."""
    return service.get_plan(plan_id)


@mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True})
def validate_simple_purchase(
    plan_id: str, account: Dict[str, Any], quote: Dict[str, Any]
) -> Dict[str, Any]:
    """Refresh account and quote before Robinhood review; block stale or unaffordable plans."""
    return service.validate_purchase(plan_id, account, quote)


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
