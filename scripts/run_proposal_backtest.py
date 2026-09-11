#!/usr/bin/env python3
"""Run the historical discovery and actual plan-generation simulation."""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from agent.proposal_backtester import ProposalPipelineBacktester
from agent.market_analyzer import MarketAnalyzer
from agent.historical_fundamentals import SecEdgarFundamentalsProvider


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--rebalance-days", type=int, default=21)
    parser.add_argument(
        "--fundamentals", choices=("sec", "none"), default="sec",
        help="Point-in-time fundamental source (default: SEC EDGAR)",
    )
    parser.add_argument("--active-only", action="store_true", help="Disable the 50% diversified ETF core")
    parser.add_argument("--minimum-holding-days", type=int, default=42)
    parser.add_argument("--maximum-turnover", type=float, default=.25,
                        help="Maximum one-way portfolio turnover per rebalance")
    parser.add_argument(
        "--allow-synthetic", action="store_true",
        help="Permit deterministic synthetic fallback (off by default)",
    )
    parser.add_argument(
        "--use-cache", action="store_true",
        help="Permit cached history (off by default because old caches lack source provenance)",
    )
    args = parser.parse_args()
    analyzer = MarketAnalyzer(
        allow_synthetic_data=args.allow_synthetic,
        allow_cached_data=args.use_cache,
    )
    provider = SecEdgarFundamentalsProvider() if args.fundamentals == "sec" else None
    result = ProposalPipelineBacktester(
        analyzer=analyzer,
        fundamentals_provider=provider,
        core_satellite=not args.active_only,
        minimum_holding_days=args.minimum_holding_days,
        maximum_one_way_turnover=args.maximum_turnover,
    ).run(
        args.start_date, args.end_date, args.capital, args.rebalance_days
    )
    metrics = result.metrics
    generated = len(result.plan_log)
    blocked = sum(item["status"] == "VALIDATION_BLOCKED" for item in result.plan_log)
    abstained = sum(item["status"] == "ABSTAINED" for item in result.plan_log)
    filled = sum(item["status"] == "SIMULATED_FILLED" for item in result.plan_log)
    blockers = Counter(
        blocker.split(":", 1)[0]
        for item in result.plan_log
        for blocker in item.get("validation", {}).get("blockers", [])
    )
    print("\n=== PROPOSAL PIPELINE BACKTEST ===")
    print(f"Period: {args.start_date} to {args.end_date} | Initial: ${args.capital:,.2f}")
    print(f"Final value: ${metrics.final_value:,.2f} | Return: {metrics.total_return_pct:+.2f}%")
    print(f"SPY: {metrics.benchmark_spy_return_pct:+.2f}% | QQQ: {metrics.benchmark_qqq_return_pct:+.2f}%")
    print(f"Max drawdown: {metrics.max_drawdown_pct:.2f}% | Volatility: {metrics.annualized_volatility_pct:.2f}%")
    print(f"Plans: {generated} | Filled: {filled} | Blocked: {blocked} | Abstained: {abstained}")
    print(f"Orders simulated: {len(result.trades_log)} | Final cash: ${result.final_cash:,.2f}")
    if blockers:
        print("Validation blockers: " + ", ".join(f"{name}={count}" for name, count in blockers.most_common()))
    print("Data sources: " + ", ".join(sorted(set(result.data_sources.values()))))
    print("Method: filing-date-filtered research + market discovery → immutable plan → next-open validation → fills")
    print(f"Portfolio: {'active-only' if args.active_only else '48% ETF core / 42% active / 10% cash'}; "
          f"minimum hold {args.minimum_holding_days}d; max one-way turnover {args.maximum_turnover:.0%}")
    if args.fundamentals == "none":
        print("Limitation: fundamentals and catalysts are unavailable and excluded from proxy scoring.")
    else:
        print("Fundamentals: SEC Company Facts known by filing date; filing recency is a catalyst proxy.")
    print()


if __name__ == "__main__":
    main()
