# Simple value and earnings workflow (V2)

V2 is intended for a small portfolio and deliberately makes fewer decisions.
ChatGPT Work performs web research; the Simple Value Trading Analysis MCP
normalizes the decision; Robinhood remains the only authority for account data,
tradability, quotes, order review, and execution.

```text
Work run -> web + primary-source research -> shortlist_value_stocks
  -> Robinhood account/positions -> propose_purchase (zero or one buy)
  -> user approval -> fresh account/quote -> validate_simple_purchase
  -> Robinhood review -> final user approval -> Robinhood placement

Monitor run -> research every holding -> evaluate_holdings
  -> HOLD / WATCH / SELL_REVIEW -> user review before any sell
```

## Why “high EPS” is not used alone

Absolute EPS changes with share price and stock splits and is not directly
comparable across companies. V2 requires positive EPS and ranks it alongside
P/E, year-over-year EPS growth, analyst-implied upside, and news sentiment. P/E
must be positive and no greater than 25. Analyst targets and predictions are
supporting evidence, never facts or sole buy/sell triggers.

## Buy policy

- Shortlist at most five stocks and propose at most one new holding per run.
- Do not add a symbol already held.
- Preserve 10% cash and cap a new position at 20% of portfolio equity.
- Require at least two sources, including a primary SEC filing or issuer
  earnings release for reported earnings claims.
- Plans expire after 24 hours and are blocked if price moves more than 5% before
  review or cash above the reserve becomes insufficient.
- No margin, leverage, options, shorts, inverse ETFs, or leveraged ETFs.
- SNOW remains restricted.

## Sell-monitor policy

The MCP proposes `SELL_REVIEW` after one severe signal or at least two ordinary
signals. Severe signals are non-positive trailing EPS or a verified material
negative event. Ordinary signals include EPS falling at least 10%, P/E above 35
or 1.5 times the sector median, a 10% earnings miss, lowered/withdrawn guidance,
an analyst target 10% below price, or strongly negative sourced news. One
ordinary signal produces `WATCH`; no signal produces `HOLD`.

Profit protection is deliberately conditional:

- A current gain of at least 20% produces `WATCH` and a thesis/valuation review,
  not an automatic sale.
- Once the position has reached a 20% gain, a decline of at least 12% from its
  highest observed price produces `SELL_REVIEW`.
- A current gain of at least 30% combined with either a 10% EPS decline or
  valuation expansion produces `SELL_REVIEW`.
- A winner can continue compounding when EPS, valuation, guidance, and price
  behavior remain supportive.

The monitor therefore requires `entry_price` and `peak_price_since_purchase`
from Robinhood/account history or a locally maintained position ledger.

## ChatGPT Work orchestration prompt

```text
Run the Simple Value Trading V2 workflow. First call get_simple_policy and
get_simple_research_requirements.

For discovery, web-search a broad set of liquid US companies for positive and
relatively high trailing EPS with a trailing P/E no greater than 25. Do not use
a fixed portfolio. Verify reported EPS and earnings claims using an SEC filing
or issuer earnings release. Use a distinct market-data source for current price
and P/E, and reputable published sources for analyst consensus, mean analyst
target, earnings date, guidance, and material news. Preserve each source's
title, publisher, URL, and observation time. Clearly label analyst forecasts as
opinions. Never fabricate unavailable fields.

Submit normalized candidates to shortlist_value_stocks. Then read the current
Robinhood account, cash, buying power, positions, tradability, fractional
eligibility, and prices. Robinhood is authoritative for those fields. Submit
the account, positions, and candidates to propose_purchase. The result may be
no trade. Present the exact proposal, sources, risks, plan ID, and cash
remaining, and ask for approval. Do not call a Robinhood order tool yet.

If I approve, refresh the Robinhood account and quote and call
validate_simple_purchase. Stop on any blocker. If ready, call Robinhood's order
review tool and show me the exact reviewed order and warnings. Place it only
after I explicitly approve that reviewed order. Never use margin, leverage,
options, shorts, inverse or leveraged ETFs, and never purchase SNOW.

For ongoing monitoring, research every current holding and call
evaluate_holdings. Include current and prior trailing EPS, P/E, sector median
P/E, entry price, highest price observed since purchase, latest earnings
surprise, guidance direction, next earnings date, analyst
target and consensus, news sentiment, material negative news, timestamp, and
sources. Report HOLD, WATCH, or SELL_REVIEW with triggering evidence. Never
sell automatically; ask me to approve an exact sell proposal first.
```
