# Point-in-Time Research and Portfolio Backtesting

## Architecture

The historical workflow deliberately keeps research, planning, validation, and
execution separate:

1. Yahoo's chart endpoint supplies historical OHLCV data for discovery,
   technical factors, risk, simulated close snapshots, and next-open fills.
2. SEC EDGAR Company Facts supplies annual fundamentals. Every observation is
   filtered on its public `filed` date relative to the simulated decision time.
3. `HistoricalDiscoveryAgent` creates the same kind of candidate set needed by
   the planner, but labels historical packets separately from live research.
4. `HistoricalMarketProxyPipeline` scores the point-in-time packet and applies
   the historical portfolio policy.
5. `TradingAnalysisService` creates the real immutable trade plan and validates
   it against next-session prices and the simulated account.
6. The simulator fills only validation-ready intents and records the resulting
   holdings, cash, trades, and benchmark equity curves.

Historical packets are accepted only by the isolated historical pipeline. They
do not weaken the live MCP contract or authorize broker execution.

## Frozen portfolio policy

- 48% diversified ETF core: SPY 19%, QQQ 19%, IWM 10%.
- 42% active stock sleeve selected by point-in-time fundamental, momentum,
  valuation, filing-recency, and risk factors.
- 10% target cash.
- 20% mandate cap; next-market-open plans construct at 95% of that cap (19%) to
  leave room for overnight price movement.
- 42 calendar-day minimum holding period.
- 25% maximum one-way turnover per rebalance.
- 21 calendar-day rebalance check by default.
- SNOW remains restricted throughout discovery, planning, and validation.

The ETF core is a construction rule, not a claim that ETF fundamentals outrank
individual securities. The three ETFs are still subject to price, liquidity,
risk, tradability, concentration, and next-open validation checks.

## Data integrity and limitations

- SEC facts published after a simulated decision date are unavailable to that
  decision. Later amendments replace earlier values only after their filing
  dates.
- Annual Company Facts are free and useful, but do not provide historical
  analyst estimates, consensus revisions, or a complete event/catalyst feed.
- Filing recency plus reported earnings growth is therefore explicitly a
  catalyst proxy. It is not historical news sentiment.
- Yahoo chart data is convenient and free but carries no institutional service
  guarantee. Production-quality evaluation should add a licensed price source
  and delisting/corporate-action coverage.
- The configured stock universe can introduce survivorship bias. A stronger
  research test should use historical index constituents or a delisting-aware
  security master.
- Backtest performance is evidence about this fixed implementation, not a
  forecast and not trading advice.

## Running and evaluating

```bash
export SEC_USER_AGENT="AgenticTrading your-email@example.com"
python3 scripts/run_proposal_backtest.py \
  --start-date 2024-09-10 \
  --end-date 2026-09-10 \
  --capital 1000
```

Fix all rules before choosing a holdout date. Run the development interval and
holdout interval separately, and compare total return, drawdown, volatility,
filled/blocked plans, turnover, and SPY/QQQ benchmarks. Do not tune parameters
on the holdout result and then continue calling it out-of-sample.

For an honest provider upgrade, implement `HistoricalResearchProvider.snapshot`
and return a `FundamentalSnapshot` containing only information known at the
requested `as_of` date. The simulator need not change.
