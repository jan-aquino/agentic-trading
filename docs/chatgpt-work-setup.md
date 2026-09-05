# Connect Trading Analysis to ChatGPT Work

For the complete copy-ready orchestration instructions, see
[ChatGPT Work orchestration prompt](chatgpt-work-orchestration-prompt.md).

## What this server is

`Trading Analysis` is a proposal-only MCP server. ChatGPT Work discovers
candidates and gathers evidence, fundamentals, technicals, catalysts, risk
metrics, tradability, and fresh Robinhood prices. The server validates and
scores those research packets, constructs a mandate-constrained portfolio,
and returns an expiring immutable plan. It has no Robinhood credentials and
exposes no order-placement tool.

The intended composition is:

```text
ChatGPT Work
  -> Robinhood MCP reads
  -> Rallies discovery and independent research
  -> Trading Analysis MCP generates a plan
  -> user reviews the exact plan
  -> Robinhood MCP reviews and places approved orders
  -> Robinhood MCP verifies order status
```

## Run locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/run_analysis_mcp.py
```

The Streamable HTTP endpoint is `http://127.0.0.1:8000/mcp`. Use the MCP
Inspector or Codex desktop to test it locally. ChatGPT Work on the web cannot
connect to this loopback address.

## Deploy for ChatGPT Work

Build the included container and deploy it behind an HTTPS endpoint with
persistent storage for `TRADING_ANALYSIS_PLAN_DIR`:

```bash
docker build -t trading-analysis-mcp .
docker run --rm -p 8000:8000 \
  -e TRADING_ANALYSIS_PLAN_DIR=/var/lib/trading-analysis/plans \
  -v trading-analysis-plans:/var/lib/trading-analysis/plans \
  trading-analysis-mcp
```

For production, put the endpoint behind an OAuth 2.1 authorization server and
configure the MCP server as a protected resource. Do not expose account
snapshots through an unauthenticated public endpoint. The Python MCP SDK's
`TokenVerifier` and `AuthSettings` interfaces support JWT verification or
token introspection. TLS termination, identity-provider configuration, and
durable encrypted storage belong in the deployment platform, not source code.

Once deployed:

1. In ChatGPT, enable Developer Mode.
2. Open **Plugins**, choose **Create plugin**, and enter
   `https://YOUR_HOST/mcp` as the remote MCP URL.
3. Connect Robinhood's Trading MCP separately using
   `https://agent.robinhood.com/mcp/trading` and complete Robinhood's Agentic
   account onboarding.
4. Start a Work task with both plugins enabled.

Install and enable the Rallies plugin in the same Work task if it will be the
research provider. Rallies does not connect directly to this MCP server:
ChatGPT Work calls Rallies, normalizes its results into the schema returned by
`get_research_requirements`, and passes those packets to `generate_trade_plan`.
No Rallies API key or SDK is required in this repository when using the plugin.

The repository's local plugin descriptor in
`plugins/trading-analysis/.mcp.json` targets the local endpoint for desktop
development. Replace its URL in a deployment-specific plugin package; do not
commit secrets or bearer tokens.

## Recommended Work instructions

```text
You orchestrate trading research but do not invent account, market, or
fundamental data. First call get_research_requirements. Read the Agentic
account and every current position from Robinhood. Use Rallies to screen a
broad, dynamic universe and research every current holding plus the strongest
new candidates. A Rallies model portfolio, AI Arena result, watchlist,
community signal, options-flow signal, or dark-pool signal may seed discovery
but is not a target portfolio or trade instruction. For material fundamental
claims, prefer primary filings or issuer evidence and provide at least two
distinct source URLs with observation times. Use Robinhood—not Rallies—as the
authority for account balances, positions, tradability, fractional eligibility,
and the current prices submitted to the analysis service. Synthesize the thesis
and conviction; do not merely copy a provider score. Submit the mandate,
account snapshot, positions, and normalized research packets to
generate_trade_plan. During regular market hours use planning_mode=immediate.
After hours, use planning_mode=next_market_open so recent closing prices may be
used for planning and candidates above the enforced 45% annualized-volatility
ceiling are rejected.
Show me the exact plan ID, expiry, warnings, and order intents. Do not place
orders yet. After I explicitly approve that exact plan ID, fetch all snapshots
again and call validate_trade_plan. Stop if execution_ready is false. For each
validated intent, call Robinhood review_equity_order and show any warnings.
Only then place the exact reviewed order, and verify it with get_equity_orders.
Never treat order submission as a fill. Never trade a restricted symbol. For a
next_market_open plan, wait until the market opens, fetch fresh Robinhood
account data and quotes, and call validate_trade_plan. Never execute directly
from closing prices. If validation reports expiry, price drift, or any other
blocker, generate a new plan instead of overriding it.
```

## Rallies beta checklist

Before enabling execution, run at least one proposal-only test with no holdings
and approximately $500 buying power:

1. Confirm Rallies and Trading Analysis appear as available tools in the Work
   task, and Robinhood is connected to the intended dedicated account.
2. Confirm `get_research_requirements` is called before screening and that the
   candidate set contains names outside any published Rallies portfolio.
3. Inspect every submitted candidate packet for all required numeric fields,
   two distinct dated evidence records, and a Robinhood-sourced price and
   tradability status.
4. Confirm weak or incomplete research is rejected or produces an abstention;
   do not fill missing data with estimates.
5. Stop after displaying the proposed plan ID, allocation, cash reserve,
   warnings, and expiry. Do not call Robinhood order placement during this
   first beta run.

If Rallies does not expose one of the required metrics, calculate it from
provider price history only when the underlying observations are available and
label the derivation in the evidence. Otherwise omit the candidate; do not
fabricate a neutral value.

## Tool contract

- `get_strategy_policy`: read the enforced policy and service boundary.
- `get_research_requirements`: read the required research packet schema.
- `generate_trade_plan`: score dynamic candidates and persist an expiring,
  mandate-driven portfolio proposal.
- `get_trade_plan`: retrieve the immutable proposal for review/audit.
- `validate_trade_plan`: compare the proposal with fresh broker data and emit
  review-ready intents or blockers.

`execution_ready: true` means only that the plan may advance to explicit user
approval and Robinhood's review tool. It is not approval and is not evidence
that an order was submitted or filled.

There is no configured candidate universe in the live pipeline. Candidate
discovery belongs to ChatGPT Work. Every current holding must have a research
packet so the optimizer never liquidates an asset it has not evaluated.
