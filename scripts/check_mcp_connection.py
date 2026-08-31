#!/usr/bin/env python3
"""Explain how to verify the official Robinhood Trading MCP connection."""

from pathlib import Path


def run_diagnostics():
    print("\n" + "=" * 80)
    print("🔍 OFFICIAL ROBINHOOD TRADING MCP CONNECTION DIAGNOSTICS")
    print("=" * 80)
    config = Path(__file__).parent.parent / "mcp_config.json"
    print(f"\nProject configuration: {config}")
    print("Expected endpoint: https://agent.robinhood.com/mcp/trading")
    print("\nVerification must run in Codex, which owns the browser-authenticated session:")
    print("  1. Call get_accounts and identify the Agentic account.")
    print("  2. Call get_portfolio with that account number.")
    print("  3. Call get_equity_positions and get_equity_quotes.")
    print("\nThis script intentionally does not use local OAuth files, passwords, or private APIs.")
    print("See ROBINHOOD_MCP_MIGRATION.md for the live execution sequence.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_diagnostics()
