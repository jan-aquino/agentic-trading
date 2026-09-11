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

Use the [canonical live-trading prompt](chatgpt-work-orchestration-prompt.md).
It is the single maintained prompt for research, approvals, execution, and monitoring.

Implementation detail: the 20% reassessment signal currently counts toward
the ordinary two-signal sell-review threshold. A gain plus one other ordinary
signal can therefore produce SELL_REVIEW below a 30% gain.
