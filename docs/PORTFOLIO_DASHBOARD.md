# Portfolio dashboard

The Portfolio Monitor answers four questions for each holding:

- Why did I buy it?
- Are EPS, P/E, and the analyst target better or worse than when I bought it?
- Is there recent news or an earnings date I should pay attention to?
- Does the strategy currently say HOLD, WATCH, or SELL REVIEW?

It is intentionally read-only. It does not connect to Robinhood and it cannot
place an order.

## Data flow

ChatGPT Work reads current account and position facts from Robinhood, researches
each holding, and calls `evaluate_holdings`. It then calls
`build_portfolio_dashboard_snapshot` with:

- Robinhood account value and cash;
- Robinhood quantity, average cost, and current price for every position;
- current holding research, news, and evidence; and
- the thesis and EPS, P/E, and analyst target saved when the position was bought.

The analysis MCP calculates returns and strategy labels and returns a
`portfolio-dashboard-v1` JSON snapshot. In Work, download that result as
`portfolio-snapshot.json`. Open the dashboard and select **Import update**.

The browser validates the snapshot and stores it in local storage. Real account
data is not part of the dashboard source and is not uploaded to the hosted
dashboard. Clearing site data or selecting **Restore example** removes the
imported snapshot from that browser.

## Run locally

From the repository root:

```bash
python3 -m http.server 4173 --directory portfolio_dashboard/dist
```

Open `http://127.0.0.1:4173`. The page starts with clearly marked example data.

## Missing history

The dashboard does not reconstruct an old buying decision from current data.
For every filled purchase, retain the original thesis, purchase date, trailing
EPS, trailing P/E, and analyst target. If a purchase record is missing, the
holding still appears using current Robinhood and research facts, but its
purchase-time metric cells show unavailable. Repair the record from the
approved proposal or fill history when possible. Do not use today's metrics
as the purchase baseline.
