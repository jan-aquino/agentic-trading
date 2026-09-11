# V2 architecture

ChatGPT Work owns web research and the authenticated brokerage connection.
The analysis server scores submitted facts and stores purchase proposals.

```text
Web research + Robinhood account reads
  -> shortlist_value_stocks -> propose_purchase -> proposal approval
  -> fresh brokerage checks -> validate_simple_purchase
  -> Robinhood review -> final approval -> placement -> status verification

Holding research + cost basis + price history
  -> evaluate_holdings -> HOLD / WATCH / SELL_REVIEW
  -> exact sell proposal and approval -> broker review/approval/placement
```

See [the workflow](SIMPLE_WORKFLOW.md), [setup](chatgpt-work-setup.md), and
[canonical prompt](chatgpt-work-orchestration-prompt.md).
V1 remains at tag v1 and in the original modules; its architecture is preserved
in [the archive](../archive/v1/architecture.md).
