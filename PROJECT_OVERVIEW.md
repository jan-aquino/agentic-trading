# Agentic Trading System

## Portfolio summary

This project is a Python-based prototype for an approval-first trading agent.
It combines technical market analysis, a rules-based allocation model, strict
portfolio constraints, and a human confirmation gate before any live brokerage
action. The public version uses Robinhood's official Trading MCP as the only
supported live integration; local Python remains a paper-trading and research
environment.

## What it demonstrates

- **Multi-signal research:** daily price history is transformed into moving
  averages, RSI, MACD, ATR, and momentum signals.
- **Rules-based portfolio construction:** the strategy blends an AI
  infrastructure universe with diversified core holdings and a cash target.
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
| Strategy and analysis | `agent/market_analyzer.py`, `agent/rallies_strategy.py` |
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
