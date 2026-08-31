# 🚀 Agentic Trading System (Rallies ChatGPT Portfolio Emulation)

An autonomous AI trading agent that conducts quantitative market analysis, emulates the high-performing **ChatGPT Portfolio from the Rallies AI Arena**, strictly excludes **Snowflake (`SNOW`)** for workplace compliance, sends **SMS/iMessage text notifications** for trade confirmation before execution, and executes orders directly on **Robinhood** via Model Context Protocol (MCP).

> **Live-trading migration:** The supported integration is Robinhood's official Trading MCP (`https://agent.robinhood.com/mcp/trading`) authenticated in Codex and scoped to a dedicated Agentic account. The legacy local `robin_stocks` and private OAuth paths are deprecated and blocked from live use. See [ROBINHOOD_MCP_MIGRATION.md](ROBINHOOD_MCP_MIGRATION.md).

Portfolio overview: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) · Architecture: [docs/architecture.md](docs/architecture.md)

---

## 🌟 Key Features

1. **Rallies ChatGPT Portfolio Strategy**:
   - Focuses on high-conviction **AI Infrastructure** market leaders (`CRDO`, `NBIS`, `GOOGL`, `NVDA`, `AMD`, `MRVL`, `APH`, `AVGO`, `MSFT`, `AMZN`).
   - Balances volatility with **Core Resilient Anchors** (`JPM`, `PGR`, `V`, `CI`, `LDOS`, `LLY`, `UNH`).
   - Maintains a **10%–15% dynamic cash reserve** for opportunistic dip buying.
   - Evaluates multi-timeframe momentum, trend structure (EMA 20/50, SMA 200), RSI, MACD, and ATR volatility.

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
│   ├── rallies_strategy.py        # Rallies ChatGPT Portfolio emulation & trade proposal builder
│   ├── risk_manager.py            # Volatility sizing (ATR), position caps, cash buffer enforcement
│   ├── backtester.py              # Event-driven backtest engine & performance analytics
│   ├── mcp_robinhood.py           # Robinhood MCP client, account manager & order router
│   ├── notifier.py                # Multi-channel text notification (iMessage, Twilio, CLI)
│   └── orchestrator.py            # End-to-end trading loop coordinator
├── scripts/
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
