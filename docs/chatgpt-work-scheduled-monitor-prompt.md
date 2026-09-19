# ChatGPT Work — scheduled V2 monitoring prompt

Use this for the scheduled, proposal-only run. It replaces the older scheduled
prompt. It does not authorize brokerage order review or execution. Before the
first scheduled run, refresh the Trading Analysis connection and confirm that
`build_portfolio_dashboard_snapshot` or its alias `build_portfolio_snapshot` is
available in a new Work task.

```text
Run my Simple Value Trading V2 scheduled workflow using real web research, the
Trading Analysis MCP, and the official Robinhood Trading connector. This run
authorizes research, account reads, saved buy proposals, holding evaluations,
and a private dashboard JSON export only. It never authorizes broker order
review, placement, cancellation, or a sale. Do not turn a proposal or a SELL
REVIEW label into an order.

1. Check session and tools before expensive work
Check the US equity market calendar and actual current time in America/New_York.
Start account checks only after the regular session has opened, normally 09:30
ET. If dispatched a few minutes early on a trading day, wait in intervals no
longer than 60 seconds and recheck until the open, for up to 10 minutes. If
still pre-open after that bound, report the timing failure. Skip market
holidays, early-close sessions that are already closed, and other sessions
already closed. Do not queue after-hours orders or claim continuous monitoring.

Before reading Robinhood or researching stocks, confirm that the connected
Trading Analysis tools include get_simple_policy,
get_simple_research_requirements, shortlist_value_stocks, propose_purchase,
evaluate_holdings, and either build_portfolio_dashboard_snapshot or
build_portfolio_snapshot. Call the two policy
and requirements tools and require policy_version simple-value-v2. If the
builder is missing, stop and report that the Work connection's tool inventory
is stale; do not repeat account reads or fabricate a dashboard file. The live
MCP endpoint is https://trading-analysis-mcp-production.up.railway.app/mcp.

2. Read the actual account
Use the intended dedicated Robinhood account. If account selection is
ambiguous, report that and stop. Read fresh account equity, cash balance,
buying power, all current equity positions, average buy prices, current
Robinhood prices, and pending equity orders. Robinhood is authoritative for
account and position facts. Do not assume an example balance or holding list.
Never use margin buying power as spendable cash. Record observation times.

3. Monitor every holding
Research each current holding with recent primary earnings releases or SEC
filings, a clearly identified market-data source, and reputable news. Obtain
current and prior trailing EPS on the same basis, trailing P/E, sector median
P/E, latest earnings surprise, guidance direction, next earnings date,
analyst target and consensus, news sentiment, any verified material negative
event, and at least two source records with title, publisher, URL, and
observed_at. Include up to five recent_news items with title, publisher, URL,
published_at, short factual summary, and positive/neutral/negative impact.
Analyst targets are forecasts, not facts. Do not invent a neutral sentiment,
earnings date, cost basis, or historical peak if evidence is missing.

Supply entry_price from the broker's average cost or supported fill history.
Supply peak_price_since_purchase from split-adjusted price history during the
actual holding period, not a 52-week high from before purchase. Call
evaluate_holdings for every fully researched position. Clearly separate HOLD,
WATCH, and SELL_REVIEW. Explain each signal in plain English. If a holding
lacks required evidence, identify the missing field and do not present an
unsupported sell judgment for it.

4. Look for at most one new purchase proposal
Only do candidate research if there is cash above the policy's 10% reserve,
no conflicting pending buy order, and a plausible new position can meet the
$5 minimum. Search a dynamic set of liquid US common stocks across sectors;
do not reuse a fixed shortlist. Verify roughly 5–10 candidates using at least
two distinct sources per candidate, including an issuer earnings release or
SEC filing. Require positive trailing GAAP diluted EPS and trailing P/E no
greater than 25. Distinguish GAAP from adjusted EPS and trailing from forward
P/E; cross-check price, EPS, and P/E. For eps_growth_yoy, compare the latest
reported quarter's GAAP diluted EPS with the same quarter a year earlier and
state that basis. Review earnings quality, debt, guidance, upcoming earnings,
news, analyst target changes, and value-trap or cyclical risks.

Use the exact fields from get_simple_research_requirements, including real
Robinhood price, tradable, and fractional_tradable values. Use decimal
percentages (10% = 0.10), timestamps, and source records. Call
shortlist_value_stocks, then propose_purchase with the fresh account,
positions, and complete researched candidate packets. It may save zero or one
buy proposal. Do not bypass the 20% position cap, 10% cash reserve, SNOW
restriction, or other policy rules. If no candidate has a supportable thesis,
or there is insufficient cash, report no proposal. If a proposal is saved,
show its plan ID, expiry, symbol, dollar amount or quantity, reference price,
thesis, sources, principal risks, and reason it fits the current portfolio.
Do not call Robinhood order review or placement in this scheduled run. A later
interactive run requires fresh checks and explicit approvals.

5. Produce the dashboard update
Call build_portfolio_dashboard_snapshot (or its identical alias
build_portfolio_snapshot) with the fresh account; every current
Robinhood position as {symbol, quantity, average_buy_price, price}; the same
fully researched holding packets used for monitoring, including recent_news;
and verified purchase_records where available. Each purchase record should
preserve symbol, company_name, purchased_at, original thesis, and the EPS,
P/E, and analyst target known when bought. Locate records from prior approved
proposals, fills, or a durable purchase ledger. Scheduled runs are independent;
do not assume access to a previous conversation. Do not use today's metrics
as a missing purchase baseline. Pass only verified purchase records; the
dashboard can show unavailable original metrics for the others.

Generate a downloadable file named portfolio-snapshot.json containing exactly
the returned portfolio-dashboard-v1 JSON object, with schema_version at the
top level. Do not add Markdown, example holdings, account credentials, or
invented data to the file. The dashboard is private and read-only; importing
this file does not place trades. Tell me to open
https://simple-value-portfolio-monitor.janalfred-aquino.chatgpt.site and use
Import update. If any holding cannot be evaluated because current research is
incomplete, report that limitation rather than claiming a complete snapshot.

6. Report briefly
Summarize account value, cash, holdings needing attention, the main upcoming
earnings or news checkpoint, whether a buy proposal was saved, and whether the
dashboard file was produced. List material missing data. State explicitly:
No orders were reviewed, placed, or cancelled. Do not claim that a scheduled
run monitors continuously between executions.
```
