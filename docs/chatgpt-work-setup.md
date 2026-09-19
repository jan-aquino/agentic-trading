# Connect V2 to ChatGPT Work

The default entry point is `scripts/run_analysis_mcp.py`, which starts
`simple_trading_mcp.server`. The original V1 instructions are archived under
`archive/v1/`.

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_analysis_mcp.py
```

Local endpoint: http://127.0.0.1:8000/mcp. A remote Work task needs the deployed
HTTPS endpoint, not localhost. The existing Dockerfile starts V2 automatically.
Persist TRADING_ANALYSIS_PLAN_DIR on the host; plans otherwise may disappear on
restart. The service itself does not implement authentication: retain or configure
appropriate authenticated access before sending real account data.

After updating the hosted service from main, refresh the analysis connection
in Work and call get_simple_policy. It must return simple-value-v2. Confirm
get_simple_research_requirements, shortlist_value_stocks, propose_purchase,
get_simple_plan, validate_simple_purchase, evaluate_holdings, and
build_portfolio_dashboard_snapshot (or its alias build_portfolio_snapshot) are
available. The checked-in Trading Analysis plugin points at the Railway URL;
ChatGPT Work may retain an older connection's tool catalog until that plugin
or MCP connection is refreshed and a new Work task is started. In ChatGPT,
open Plugins, select the Trading Analysis connection, and choose Refresh.
Verify its endpoint is
`https://trading-analysis-mcp-production.up.railway.app/mcp` and that its tool
list includes a dashboard builder. If Refresh is unavailable, reconnect the
MCP endpoint or ask the workspace plugin owner to publish an updated version.
A Git push alone does not establish that the remote server has deployed.

Connect Robinhood separately to the intended account and enable web research.
Rallies is optional; it is no longer a prerequisite. Plugin capabilities depend
on the task and account connections; see [official plugin documentation](https://learn.chatgpt.com/docs/plugins).

Use the [canonical live-trading prompt](chatgpt-work-orchestration-prompt.md).
It covers actual research, account reads, proposal approval, fresh checks,
broker review, final approval, placement, and verification.

V2 validation checks plan expiry, account identity, price drift, and cash.
The orchestrator also checks current positions, pending orders, tradability,
regular market hours, and resulting concentration. These are not all enforced
by the simplified service itself. Monitoring returns recommendations and
requires a sourced cost basis and historical peak; no background schedule or
persistent position ledger is created merely by pasting the prompt.
