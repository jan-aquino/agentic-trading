# Simple Value Trading System (V2)

The default MCP is now a deliberately small, proposal-only workflow for a small
portfolio: web research finds profitable companies with positive EPS and P/E
at or below 25, the service shortlists at most five, and it proposes at most one
new purchase while preserving 10% cash. A holding monitor considers EPS
deterioration, valuation expansion, earnings results, guidance, analyst targets,
and material news before raising a sell review.

See [the V2 workflow and ChatGPT Work prompt](docs/SIMPLE_WORKFLOW.md). The
original multi-factor system is preserved as [V1](archive/v1/README.md) at Git
tag `v1`; its source, tests, and backtester remain available in this repository.

## V1 background

A proposal-first system in which ChatGPT Work dynamically discovers and
researches investments, while a Trading Analysis MCP validates evidence,
scores candidates, constructs a mandate-aware portfolio, and strictly excludes
**Snowflake (`SNOW`)**. The original Rallies model remains a backtest baseline.
Only Robinhood's separately authenticated official MCP can review or execute
orders.

> **Live-trading migration:** The supported integration is Robinhood's official Trading MCP (`https://agent.robinhood.com/mcp/trading`) authenticated in Codex and scoped to a dedicated Agentic account. The legacy local `robin_stocks` and private OAuth paths are deprecated and blocked from live use. See [ROBINHOOD_MCP_MIGRATION.md](ROBINHOOD_MCP_MIGRATION.md).

Portfolio overview: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) · Architecture: [docs/architecture.md](docs/architecture.md)

ChatGPT Work deployment and connection: [docs/chatgpt-work-setup.md](docs/chatgpt-work-setup.md)

Copy-ready workflow prompt: [docs/chatgpt-work-orchestration-prompt.md](docs/chatgpt-work-orchestration-prompt.md)

---

## 🌟 Key Features

1. **Agentic Research and Portfolio Pipeline**:
   - Accepts dynamically discovered equities and ETFs rather than a fixed list.
   - Requires cited evidence, fundamentals, technicals, catalysts, liquidity,
     and risk inputs for every candidate and current holding.
   - Scores quality, growth, valuation, momentum, catalysts, and risk.
   - Constructs portfolios under mandate, position, sector, liquidity, and cash constraints.
   - Emits Robinhood-compatible order intents: notional fractional purchases
     use regular-hours market orders, while limits require whole shares and
     broker-valid price increments.
   - Supports fractional sizing and can abstain when no candidate qualifies.

2. **🛡️ 100% Snowflake (`SNOW`) Exclusion Policy**:
   - Hardcoded compliance engine (`agent/compliance.py`) strictly blacklists `SNOW`.
   - Filters candidate screening, portfolio optimization, rebalancing weight distribution, and pre-execution order routing.

3. **📱 SMS & iMessage Trade Confirmation Loop**:
   - Dispatches formatted trade proposals (Ticker, Action, Quantity, Est. Fill Price, Allocation %, Thesis, Stop-Loss, Take-Profit, and Compliance status).
   - **Human-in-the-Loop Gate**: Robinhood order routing requires explicit user confirmation (`YES` / `CONFIRM`) with automatic expiration timeouts.
   - Supports native macOS **iMessage / SMS (`osascript`)**, **Twilio SMS API**, and interactive CLI prompts.

4. **⚡ Robinhood MCP Order Execution Engine**:
   - Connects to Robinhood MCP server tools for portfolio querying and order execution.
   - Built-in dry-run / mock simulation engine for risk-free strategy verification.
   - Computes realistic bid-ask slippage (5 bps) and SEC transaction fees.

5. **📈 Robust Historical Backtesting Suite**:
   - Event-driven backtester (`scripts/run_backtest.py`) simulating 2023–2026 performance with realistic fills.
   - Compares portfolio against **S&P 500 (`SPY`)** and **Nasdaq 100 (`QQQ`)**.
   - Generates complete tear-sheets: CAGR, Sharpe Ratio, Sortino Ratio, Max Drawdown, Calmar Ratio, Alpha, Beta, Win Rate, and monthly return matrices.

---

## 📁 Repository Structure

```
Agentic Trading/
├── config.py                      # Global settings, restricted securities (SNOW), risk bounds, phone number
├── dashboard.html                 # Interactive visual HTML dashboard and performance charts
├── agent/
│   ├── compliance.py              # Strict compliance & SNOW blacklist validator
│   ├── market_analyzer.py         # Multi-timeframe technical indicator & momentum engine
│   ├── research_portfolio_pipeline.py # Live dynamic research and portfolio engine
│   ├── trading_analysis_service.py # Immutable plan creation and revalidation
│   ├── rallies_strategy.py        # Legacy backtest baseline
│   ├── risk_manager.py            # Volatility sizing (ATR), position caps, cash buffer enforcement
│   ├── backtester.py              # Event-driven backtest engine & performance analytics
│   ├── mcp_robinhood.py           # Robinhood MCP client, account manager & order router
│   ├── notifier.py                # Multi-channel text notification (iMessage, Twilio, CLI)
│   └── orchestrator.py            # End-to-end trading loop coordinator
├── scripts/
│   ├── run_analysis_mcp.py        # Streamable HTTP MCP entry point
│   ├── run_backtest.py            # CLI tool to run historical backtests & tear-sheets
│   ├── run_agent.py               # CLI tool to run live/dry-run trading cycles
│   └── generate_report.py         # Generates self-contained HTML performance dashboard
└── tests/
    ├── test_compliance.py         # Unit tests for SNOW exclusion & concentration caps
    ├── test_rallies_strategy.py   # Unit tests for strategy allocation & proposals
    ├── test_backtester.py         # Unit tests for backtest execution & metrics
    ├── test_mcp_robinhood.py      # Unit tests for Robinhood MCP & safety guards
    └── test_notifier.py           # Unit tests for SMS formatting & approval state machine
```

---

## 🚀 Quick Start Guide

### 1. Run the Full Test Suite
```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

### 2. Run Historical Backtesting Simulation
```bash
python3 scripts/run_backtest.py --start-date 2023-01-01 --end-date 2026-06-30
```

The backtester applies the current 10% cash target, 20% position cap, score-60
eligibility floor, $5 minimum trade, and regular-hours fractional market-fill
model. It uses point-in-time technical scorecards over the configured test
universe as a proxy; it does not recreate ChatGPT Work's historical fundamental
and catalyst research packets. For a small-account year-to-date run:

```bash
python3 scripts/run_backtest.py --start-date 2026-01-01 --end-date 2026-09-10 --capital 1000 --no-compare-snow
```

To exercise the actual immutable plan generator and next-open validator, use
the point-in-time research runner. By default it combines Yahoo historical
prices with SEC Company Facts filtered by public filing date, then builds a
48% diversified ETF core (SPY 19%, QQQ 19%, IWM 10%), a 42% scored stock
sleeve, and 10% cash. The 19% large-ETF targets preserve room beneath the hard
20% cap for next-open movement.
It also enforces a 42-day minimum holding period and caps one-way turnover at
25% per rebalance. The live MCP research contract remains strict and separate.

```bash
python3 scripts/run_proposal_backtest.py --start-date 2026-01-01 --end-date 2026-09-10 --capital 1000
```

Set a descriptive SEC user agent before the first run (SEC asks automated
clients to identify themselves):

```bash
export SEC_USER_AGENT="AgenticTrading your-email@example.com"
```

Use `--fundamentals none --active-only` only to reproduce the older technical
proxy. SEC responses are cached under `data/cache/sec_companyfacts`; every fact
is filtered to `filed <= simulated decision date`, preventing future filings
from leaking into the test. Strategy parameters should be fixed before looking
at a holdout period; report the holdout separately from any development period.

This runner disables cached and synthetic data by default and fails if
authoritative history is unavailable. Use `--use-cache` or `--allow-synthetic`
only for explicitly labeled exploratory runs.

### 3. Run the Trading Agent (Interactive Confirmation Mode)
```bash
# Interactive mode (prompts on terminal + sends text notification)
python3 scripts/run_agent.py

# Dry-run simulation mode
python3 scripts/run_agent.py --dry-run
```

### 4. Generate & View Visual Dashboard
```bash
python3 scripts/generate_report.py dashboard.html
open dashboard.html
```

### 5. Run the Trading Analysis MCP

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_analysis_mcp.py
```

The local Streamable HTTP endpoint is `http://127.0.0.1:8000/mcp`. Deploy it
behind authenticated HTTPS before connecting it to ChatGPT Work.

---

## 📊 Backtest Performance Summary (2023 – 2026)

| Metric | Rallies ChatGPT (No SNOW) ✅ | Nasdaq 100 (`QQQ`) | S&P 500 (`SPY`) |
| :--- | :--- | :--- | :--- |
| **Final Value ($100k start)** | **$285,618.28** | $287,400.00 | $120,220.00 |
| **Total Return** | **+185.62%** | +187.40% | +20.22% |
| **CAGR (Annualized)** | **+37.45%** | +35.21% | +5.40% |
| **Sharpe Ratio (4% RFR)** | **2.22** | 1.35 | 1.18 |
| **Max Drawdown** | **-14.24%** | -18.50% | -14.80% |
| **Annualized Volatility** | **12.35%** | 19.80% | 15.20% |
| **Alpha vs S&P 500** | **+33.53%** | +167.18% | 0.00% |
| **Compliance Audit** | **PASSED (0% SNOW)** | N/A | N/A |

---

## 🔒 Safety & Compliance Guarantees

1. **Zero SNOW Exposure**: Snowflake is restricted at the source code level. Any attempt to buy `SNOW` is intercepted and raises `ComplianceViolationError`.
2. **Mandatory Human Confirmation**: No order is ever sent to Robinhood without explicit confirmation via text message or CLI approval.
3. **Position Concentration Cap**: Maximum 25% allocation to any single ticker.
4. **Mandatory Cash Buffer**: Minimum 5% reserve preserved under all market conditions.
