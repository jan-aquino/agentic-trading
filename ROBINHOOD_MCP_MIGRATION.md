# Official Robinhood Trading MCP migration

This project now treats the official Robinhood Trading MCP as the only live
broker connection:

`https://agent.robinhood.com/mcp/trading`

Connect it in Codex using **Settings → MCP servers → Streamable HTTP**, then
complete the Robinhood browser authentication and Agentic account onboarding.
The authenticated connection is owned by Codex, so credentials, MFA secrets,
and bearer tokens must not be stored in `.env` or source code.

## Account scope

The MCP can read the user's Robinhood accounts, but it can place orders only
in the dedicated account that Robinhood reports as agent-accessible. In this
workspace that is the account nicknamed `Agentic`; use `get_accounts` to
discover the full account number at runtime and `get_portfolio` for the
authoritative buying power.

## Required live execution sequence

1. Run the local strategy and risk checks in paper mode.
2. Read `get_accounts`, `get_portfolio`, and `get_equity_positions` through
   the official MCP.
3. Preserve the project's restricted-ticker and human-approval gates.
4. Call `review_equity_order` using the agent-accessible account.
5. Treat any nonempty preview validation alert as a failed review. Show all
   broker disclosures and obtain the second explicit approval for the exact
   reviewed intents.
6. After explicit approval, call `place_equity_order` with the UUID idempotency
   key persisted in each intent. Reuse that key only to retry the same logical
   order.
7. Confirm the final broker state with `get_equity_orders`; never treat an
   order-submission response or estimated price as a fill.

## Equity-order compatibility

- Dollar-amount and fractional-share orders must be market orders submitted
  during regular market hours.
- Limit orders must use whole-share quantities. Prices above $1 use whole-cent
  increments; the raw reference quote remains separately recorded.
- Never silently convert an approved amount type, order type, quantity, price,
  or market-hours instruction. If review rejects an immutable intent, stop.
- An expired Trading Analysis plan is a hard blocker. It cannot be revived or
  extended; generate a replacement only under new user direction.

## Deprecated paths

The local `mcp_server/` implementation and `scripts/robinhood_oauth_login.py`
are legacy mock/experimental code. They use private, reverse-engineered
authentication behavior and must not be used for live trading. They remain in
the local workspace temporarily for reference, but are excluded from the
public portfolio repository.

The standalone `RobinhoodMCPClient` now fails closed in live mode. This is
intentional: it prevents a network/authentication failure from being recorded
as a successful trade. Use Codex's authenticated official MCP for all live
broker reads and writes.
