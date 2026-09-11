# Architecture

```mermaid
flowchart TD
    Trigger[User or Work task] --> Work[ChatGPT Work orchestrator]
    Work --> RHRead[Robinhood MCP reads\naccount · positions · tradability · quotes]
    RHRead --> Work
    Work --> Research[Rallies or another research provider\ndiscovery · fundamentals · filings\ntechnicals · catalysts · risk]
    Research --> Analysis
    Work --> Analysis[Trading Analysis MCP\nproposal-only service]
    Analysis --> Strategy[Evidence validation · scoring\nportfolio construction · compliance]
    Strategy --> Plan[Immutable expiring trade plan]
    Plan --> Work
    Work --> Revalidate[Fresh Robinhood reads\nand plan revalidation]
    Revalidate --> Approval{Explicit approval of\nexact plan ID?}
    Approval -- No / timeout --> Audit[Audit trail]
    Approval -- Yes --> Review[Robinhood MCP\nreview_equity_order]
    Review --> Broker{Warnings and limits pass?}
    Broker -- No --> Audit
    Broker -- Yes --> Execute[Robinhood MCP\nplace_equity_order]
    Execute --> Verify[Robinhood MCP\nget_equity_orders]
    Verify --> Audit
    Backtest[Backtester] -. validates .-> Strategy
```

## Execution principle

The workflow is deliberately proposal-first. ChatGPT Work owns orchestration
and both MCP connections. The Trading Analysis MCP receives snapshots and
returns plans but has no broker credentials or execution tools. Live account
reads, order review, placement, and verification are performed only through
the separately authenticated official Robinhood Trading MCP.

See [ChatGPT Work setup](chatgpt-work-setup.md) for deployment and connection
instructions.

The legacy Rallies strategy remains solely as a backtest and comparison
baseline. It is not used by the Trading Analysis MCP. This is distinct from
using the read-only Rallies plugin as an external research provider: ChatGPT
Work can use that plugin to assemble candidate packets, but Rallies portfolios
or AI rankings are never accepted as target allocations without the normal
evidence validation and portfolio scoring.
