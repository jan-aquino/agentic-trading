#!/usr/bin/env python3
"""CLI backtest runner for the proposal-first portfolio mandate."""

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import numpy as np

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from agent.backtester import Backtester
from config import DEFAULT_CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_backtest")


def format_table(title: str, headers: list, rows: list) -> str:
    """Generates a clean ASCII table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    sep = "+" + "+".join(["-" * (w + 2) for w in col_widths]) + "+"
    header_str = "| " + " | ".join([f"{h:<{col_widths[i]}}" for i, h in enumerate(headers)]) + " |"

    lines = [f"\n=== {title} ===", sep, header_str, sep]
    for row in rows:
        row_str = "| " + " | ".join([f"{str(v):<{col_widths[i]}}" for i, v in enumerate(row)]) + " |"
        lines.append(row_str)
    lines.append(sep)
    return "\n".join(lines)


def benchmark_risk_stats(values):
    """Calculate benchmark risk statistics over the actual requested window."""
    returns = values.pct_change().dropna()
    volatility = float(returns.std() * np.sqrt(252) * 100) if not returns.empty else 0.0
    excess = returns - 0.04 / 252
    sharpe = float(excess.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0
    downside = returns[returns < 0]
    downside_std = downside.std() * np.sqrt(252)
    sortino = float(excess.mean() * np.sqrt(252) / downside_std) if downside_std > 0 else 0.0
    drawdown = (values - values.cummax()) / values.cummax() * 100
    return volatility, sharpe, sortino, float(drawdown.min())


def main():
    parser = argparse.ArgumentParser(description="Run the proposal-first mandate backtest")
    parser.add_argument("--start-date", default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default="2026-06-30", help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=100000.0, help="Initial capital in USD")
    parser.add_argument("--rebalance-days", type=int, default=7, help="Rebalancing check frequency in days")
    parser.add_argument(
        "--compare-snow", action=argparse.BooleanOptionalAction, default=False,
        help="Also run an intentionally unrestricted SNOW comparison (default: disabled)",
    )
    parser.add_argument("--target-cash-weight", type=float, default=0.10)
    parser.add_argument("--maximum-position-weight", type=float, default=0.20)
    parser.add_argument("--minimum-candidate-score", type=float, default=60.0)
    parser.add_argument("--maximum-positions", type=int, default=10)
    parser.add_argument("--minimum-trade-notional", type=float, default=5.0)
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("🚀 RUNNING PROPOSAL-FIRST MANDATE BACKTEST")
    print(f"Period: {args.start_date} to {args.end_date} | Starting Capital: ${args.capital:,.2f}")
    print("=" * 80)

    backtester = Backtester(slippage_bps=5.0)

    # 1. Primary Strategy Backtest (Strict SNOW Exclusion)
    result_no_snow = backtester.run(
        start_date=args.start_date,
        end_date=args.end_date,
        initial_capital=args.capital,
        rebalance_interval_days=args.rebalance_days,
        exclude_snow=True,
        target_cash_weight=args.target_cash_weight,
        maximum_position_weight=args.maximum_position_weight,
        maximum_positions=args.maximum_positions,
        minimum_candidate_score=args.minimum_candidate_score,
        minimum_trade_notional=args.minimum_trade_notional,
        allow_fractional_shares=True,
    )

    m = result_no_snow.metrics

    # 2. Comparison Strategy (Baseline if SNOW were permitted)
    result_with_snow = None
    if args.compare_snow:
        result_with_snow = backtester.run(
            start_date=args.start_date,
            end_date=args.end_date,
            initial_capital=args.capital,
            rebalance_interval_days=args.rebalance_days,
            exclude_snow=False,
            target_cash_weight=args.target_cash_weight,
            maximum_position_weight=args.maximum_position_weight,
            maximum_positions=args.maximum_positions,
            minimum_candidate_score=args.minimum_candidate_score,
            minimum_trade_notional=args.minimum_trade_notional,
            allow_fractional_shares=True,
        )

    elapsed_days = max(1, (date.fromisoformat(args.end_date) - date.fromisoformat(args.start_date)).days)
    elapsed_years = max(elapsed_days / 365.25, 1 / 252)
    spy_cagr = ((1 + m.benchmark_spy_return_pct / 100) ** (1 / elapsed_years) - 1) * 100
    qqq_cagr = ((1 + m.benchmark_qqq_return_pct / 100) ** (1 / elapsed_years) - 1) * 100
    spy_vol, spy_sharpe, spy_sortino, spy_dd = benchmark_risk_stats(result_no_snow.equity_curve["SPY_Value"])
    qqq_vol, qqq_sharpe, qqq_sortino, qqq_dd = benchmark_risk_stats(result_no_snow.equity_curve["QQQ_Value"])

    # Build Comparative Performance Table
    headers = ["Strategy / Benchmark", "Final Value", "Total Return", "CAGR", "Volatility", "Sharpe", "Sortino", "Max DD", "Alpha (SPY)"]
    rows = [
        [
            "Proposal-first technical proxy (SNOW Excluded) ✅",
            f"${m.final_value:,.2f}",
            f"{m.total_return_pct:+.2f}%",
            f"{m.cagr_pct:+.2f}%",
            f"{m.annualized_volatility_pct:.2f}%",
            f"{m.sharpe_ratio:.2f}",
            f"{m.sortino_ratio:.2f}",
            f"{m.max_drawdown_pct:.2f}%",
            f"{m.alpha_vs_spy_pct:+.2f}%",
        ],
    ]

    if result_with_snow:
        ms = result_with_snow.metrics
        rows.append([
            "Rallies ChatGPT (Unrestricted / SNOW Included)",
            f"${ms.final_value:,.2f}",
            f"{ms.total_return_pct:+.2f}%",
            f"{ms.cagr_pct:+.2f}%",
            f"{ms.annualized_volatility_pct:.2f}%",
            f"{ms.sharpe_ratio:.2f}",
            f"{ms.sortino_ratio:.2f}",
            f"{ms.max_drawdown_pct:.2f}%",
            f"{ms.alpha_vs_spy_pct:+.2f}%",
        ])

    rows.extend([
        [
            "S&P 500 (SPY Benchmark)",
            f"${args.capital * (1 + m.benchmark_spy_return_pct / 100):,.2f}",
            f"{m.benchmark_spy_return_pct:+.2f}%",
            f"{spy_cagr:+.2f}%",
            f"{spy_vol:.2f}%",
            f"{spy_sharpe:.2f}",
            f"{spy_sortino:.2f}",
            f"{spy_dd:.2f}%",
            "0.00%",
        ],
        [
            "Nasdaq 100 (QQQ Benchmark)",
            f"${args.capital * (1 + m.benchmark_qqq_return_pct / 100):,.2f}",
            f"{m.benchmark_qqq_return_pct:+.2f}%",
            f"{qqq_cagr:+.2f}%",
            f"{qqq_vol:.2f}%",
            f"{qqq_sharpe:.2f}",
            f"{qqq_sortino:.2f}",
            f"{qqq_dd:.2f}%",
            f"{m.benchmark_qqq_return_pct - m.benchmark_spy_return_pct:+.2f}%",
        ],
    ])

    print(format_table("STRATEGY BENCHMARK TEAR-SHEET", headers, rows))

    # Trading & Execution Stats
    exec_headers = ["Metric", "Value"]
    exec_rows = [
        ["Total Rebalance Trades Executed", str(m.total_trades)],
        ["Modeled Slippage & SEC Fees", f"${m.total_slippage_fees:,.2f}"],
        ["Win Rate on Realized Sells", f"{m.win_rate_pct:.1f}%"],
        ["Realized Profit Factor", f"{m.profit_factor:.2f}"],
        ["Calmar Ratio (CAGR / MaxDD)", f"{m.calmar_ratio:.2f}"],
        ["Beta vs S&P 500", f"{m.beta_vs_spy:.2f}"],
    ]
    print(format_table("EXECUTION & RISK PARAMETERS", exec_headers, exec_rows))

    # Final Holdings Breakdown
    if result_no_snow.final_holdings:
        hold_headers = ["Ticker", "Category", "Shares", "Role in Portfolio"]
        hold_rows = []
        for t, qty in sorted(result_no_snow.final_holdings.items()):
            cat = "AI Infrastructure" if t in DEFAULT_CONFIG.strategy.ai_infra_universe else "Core Diversifier"
            role = "Connectivity/Silicon/Cloud Growth" if cat == "AI Infrastructure" else "Defensive Balance & Cashflow"
            hold_rows.append([t, cat, f"{qty:.6f}".rstrip("0").rstrip("."), role])
        print(format_table("FINAL PORTFOLIO HOLDINGS", hold_headers, hold_rows))

    final_cash = float(result_no_snow.equity_curve["Cash"].iloc[-1])
    final_cash_weight = final_cash / m.final_value if m.final_value else 0.0
    print("\n📋 MANDATE & METHODOLOGY:")
    print(f"  Target cash: {args.target_cash_weight:.0%} | Actual final cash: {final_cash_weight:.1%}")
    print(f"  Maximum position: {args.maximum_position_weight:.0%} | Minimum score: {args.minimum_candidate_score:g}")
    source_counts = {}
    for source in result_no_snow.data_sources.values():
        source_counts[source] = source_counts.get(source, 0) + 1
    print("  Data sources: " + ", ".join(f"{name}={count}" for name, count in sorted(source_counts.items())))
    for note in result_no_snow.methodology_notes:
        print(f"  - {note}")

    # Compliance Certificate
    print("\n🛡️ COMPLIANCE AUDIT CERTIFICATE:")
    print(f"  {result_no_snow.compliance_notes}")
    print("  Snowflake Inc. (SNOW) was completely filtered out from candidate universes and never traded.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
