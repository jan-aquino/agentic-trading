# Architecture

```mermaid
flowchart LR
    Market[Market data\nprice history & quotes] --> Analysis[Market analyzer\nEMA · RSI · MACD · ATR]
    Analysis --> Strategy[Portfolio strategy\ntarget weights & trade proposals]
    Portfolio[Robinhood Agentic account\npositions & buying power] --> Strategy

    Strategy --> Compliance[Compliance engine\nblock SNOW]
    Compliance --> Risk[Risk manager\nposition cap · cash buffer · sizing]
    Risk --> Notify[Proposal notification\ntrade ticket & expiry]
    Notify --> Approval{Explicit user\napproval?}
    Approval -- No / timeout --> Audit[Audit trail\nrejection recorded]
    Approval -- Yes --> Review[Official Robinhood MCP\nreview equity order]
    Review --> Broker{Broker warnings\nand checks pass?}
    Broker -- No --> Audit
    Broker -- Yes --> Execute[Official Robinhood MCP\nplace equity order]
    Execute --> Verify[Fetch order status\nverify terminal result]
    Verify --> Audit

    Backtest[Backtester & dashboard] -. validates strategy .-> Strategy
```

## Execution principle

The workflow is deliberately proposal-first. Local code can research,
backtest, and simulate. Live account reads and orders are performed only via
the browser-authenticated official Robinhood Trading MCP, with an explicit
approval and a post-submission verification step.
