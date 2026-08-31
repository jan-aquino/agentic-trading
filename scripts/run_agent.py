#!/usr/bin/env python3
"""
CLI Runner for the Autonomous Trading Agent.
Conducts live market analysis, computes Rallies ChatGPT Portfolio allocations (excluding SNOW),
sends text notifications for human confirmation, and executes trades on Robinhood via MCP.
"""

import argparse
import logging
import sys
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from agent.orchestrator import AgentOrchestrator
from config import DEFAULT_CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_agent")


def print_account_summary(account, positions):
    print("\n" + "=" * 70)
    print("💼 ROBINHOOD PORTFOLIO STATUS")
    print("=" * 70)
    print(f"Account:        {account.account_number}")
    print(f"Total Equity:   ${account.portfolio_equity:,.2f}")
    print(f"Buying Power:   ${account.buying_power:,.2f}")
    print(f"Cash Balance:   ${account.cash_balance:,.2f}")
    print("-" * 70)
    if not positions:
        print("No open equity positions (100% Cash Buffer).")
    else:
        print(f"{'Ticker':<8} {'Shares':<8} {'Avg Price':<12} {'Current':<12} {'Market Value':<14} {'Unrealized PnL':<15}")
        print("-" * 70)
        for p in positions:
            pnl_str = f"${p.unrealized_pnl:+,.2f} ({p.unrealized_pnl_pct:+.1f}%)"
            print(f"{p.ticker:<8} {p.quantity:<8} ${p.average_buy_price:<11.2f} ${p.current_price:<11.2f} ${p.market_value:<13.2f} {pnl_str:<15}")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run Rallies ChatGPT Portfolio Trading Agent")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without real order routing")
    parser.add_argument("--interactive", action="store_true", default=True, help="Prompt user interactively for confirmation")
    parser.add_argument("--non-interactive", dest="interactive", action="store_false", help="Do not prompt interactively (auto-approve or use SMS)")
    parser.add_argument("--once", action="store_true", default=False, help="Run single analysis/rebalance cycle and exit")
    parser.add_argument("--daemon", action="store_true", default=False, help="Run continuously as a background service")
    parser.add_argument("--interval-hours", type=float, default=24.0, help="Interval in hours between market analysis cycles in daemon mode (default: 24.0)")
    parser.add_argument("--phone", type=str, default=None, help="Target phone number for text notifications")
    args = parser.parse_args()

    config = DEFAULT_CONFIG
    if args.phone:
        config.notifier.phone_number = args.phone

    print("\n" + "=" * 80)
    print("🤖 STARTING AGENTIC TRADING SYSTEM (RALLIES CHATGPT EMULATION)")
    print("Strategy: AI Infrastructure + Core Anchors (Strict Snowflake / SNOW Exclusion)")
    print(f"Cadence:  Rebalancing check every {config.strategy.rebalance_frequency_days} days (or on-demand)")
    print(f"Notification Channel: {config.notifier.primary_channel.upper()} to {config.notifier.phone_number}")
    print(f"Robinhood Mode: {'MOCK SIMULATOR' if config.robinhood.use_mock else 'LIVE MCP BROKER'}")
    print("=" * 80)

    orchestrator = AgentOrchestrator(config)

    def execute_single_cycle():
        acc = orchestrator.robinhood.get_account_summary()
        pos = orchestrator.robinhood.get_positions()
        print_account_summary(acc, pos)

        summary = orchestrator.run_cycle(interactive=args.interactive, dry_run=args.dry_run)

        print("\n" + "=" * 80)
        print("📊 TRADING CYCLE EXECUTION REPORT")
        print("=" * 80)
        print(f"Timestamp:              {summary.timestamp}")
        print(f"Compliance Status:      {summary.compliance_certificate}")
        print(f"Trades Executed:        {len(summary.executed_trades)}")
        print(f"Trades Rejected/Aborted: {len(summary.rejected_trades)}")

        if summary.executed_trades:
            print("\n✅ Executed Order Receipts:")
            for r in summary.executed_trades:
                print(f"  • [{r.order_id}] {r.action} {r.quantity} {r.ticker} @ ${r.executed_price:.2f} (Total: ${r.total_amount:,.2f}) - Status: {r.status}")

        if summary.rejected_trades:
            print("\n⚠️ Rejected / Cancelled Orders:")
            for r in summary.rejected_trades:
                print(f"  • {r['action']} {r['ticker']} - Reason: {r['reason']}")

        if summary.account_after:
            print_account_summary(summary.account_after, summary.current_positions)

    if args.daemon:
        print(f"\n🔄 Running in DAEMON mode (Cycling every {args.interval_hours} hours)... Press Ctrl+C to stop.\n")
        while True:
            try:
                execute_single_cycle()
                print(f"\n⏳ Sleeping for {args.interval_hours} hours until next market scan...")
                time.sleep(args.interval_hours * 3600)
            except KeyboardInterrupt:
                print("\n🛑 Daemon stopped by user.")
                break
    else:
        execute_single_cycle()


if __name__ == "__main__":
    main()
