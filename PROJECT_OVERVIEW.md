# Agentic Trading System

## Portfolio summary

This project is a Python-based prototype for an approval-first trading agent.
ChatGPT Work performs dynamic candidate discovery and evidence gathering. A
proposal-only MCP validates the research, scores candidates across six factors,
constructs a mandate-aware portfolio, and requires a human confirmation gate
before the separate Robinhood MCP performs any brokerage action.

## What it demonstrates

- **Dynamic research:** there is no fixed live candidate universe; Work can use
  scans, watchlists, search, and external authoritative evidence.
- **Multi-factor selection:** quality, growth, valuation, momentum, catalysts,
  and risk are confidence-adjusted and compared consistently.
- **Mandate-driven construction:** objective, horizon, risk tolerance, sector
  caps, position caps, liquidity, cash, and fractional eligibility shape trades.
- **Risk controls:** volatility-aware sizing, a 25% single-position cap, and
  a 5% minimum cash reserve are enforced before execution.
- **Compliance by design:** `SNOW` is prohibited in the screening,
  allocation, risk, and execution layers.
- **Human-in-the-loop execution:** proposed orders require review and explicit
  approval; a broker response is not treated as a fill until order status is
  verified.
- **Testable workflow:** unit tests cover compliance, allocation, backtesting,
  notification formatting, and fail-closed live-broker behavior.

## System boundaries

The project is an educational portfolio prototype, not investment advice or a
production trading service. Historical backtest results are illustrative,
exclude taxes and changing market conditions, and do not predict future
performance. Brokerage credentials, account data, cached market data, and
trade history are intentionally excluded from this repository.

## Key assets

| Area | Primary files |
| --- | --- |
| Live research and portfolio engine | `agent/research_portfolio_pipeline.py`, `agent/trading_analysis_service.py` |
| Legacy backtest baseline | `agent/market_analyzer.py`, `agent/rallies_strategy.py` |
| Risk and compliance | `agent/risk_manager.py`, `agent/compliance.py` |
| Workflow orchestration | `agent/orchestrator.py`, `agent/mcp_robinhood.py` |
| Backtesting and reports | `agent/backtester.py`, `scripts/run_backtest.py`, `dashboard.html` |
| Verification | `tests/` |

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install numpy pandas
.venv/bin/python -m unittest discover -s tests -p "test_*.py" -v
.venv/bin/python scripts/run_backtest.py --start-date 2023-01-01 --end-date 2026-06-30
```

Use `python scripts/run_agent.py --dry-run` for simulated proposal generation.
For the official live workflow and its safety requirements, see
[`ROBINHOOD_MCP_MIGRATION.md`](ROBINHOOD_MCP_MIGRATION.md).
