# V1 archive

V1 is preserved in Git at tag `v1` and commit `4b39f33`. It contains the full
multi-factor research/portfolio pipeline, point-in-time SEC backtester,
core-satellite allocation, turnover controls, and original Trading Analysis MCP.

The V1 implementation remains in these packages so its code and tests can be
reused without copying a second source tree:

- `trading_analysis_mcp/`
- `agent/trading_analysis_service.py`
- `agent/research_portfolio_pipeline.py`
- `agent/proposal_backtester.py`
- `agent/historical_fundamentals.py`
- `agent/historical_research_proxy.py`
- `scripts/run_proposal_backtest.py`
- `docs/POINT_IN_TIME_RESEARCH.md`

To inspect or restore the exact archived repository without disturbing V2:

```bash
git show v1:README.md
git worktree add ../agentic-trading-v1 v1
```

V2 is the default MCP server entry point. V1 is not deleted and its backtests remain
available, but it is no longer the recommended personal workflow.
