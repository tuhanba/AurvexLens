# 01 — Safety & isolation boundaries

Source: `docs/03_phase0_spec.md` §3, §4.

## Primary boundaries (broker / terminal level)
1. **Separate terminal.** Aurvex Lens connects only to the explicit `terminal_path` via `initialize(path=...)`.
   `login` / `password` / `server` are never passed.
2. **Investor access.** The user logs in manually with the investor password; the broker rejects orders
   from an investor session.
3. **Identity verification** (`src/aurvex_lens/bridge/identity.py`), before any market data is read:

| Check | Field | Expected | On mismatch |
|---|---|---|---|
| I2 (pre) | configured `terminal_path` | not in `forbidden_terminal_paths` | FAIL, `initialize()` never called |
| I1 | `terminal_info().path` | folder of configured `terminal_path` | FAIL |
| I2 (post) | `terminal_info().path` | not a forbidden terminal folder | FAIL |
| I3 | `account_info().login` | `expected_login` | FAIL |
| I4 | `account_info().server` | `expected_server` | FAIL |
| I5 | `account_info().trade_allowed` | `False` | FAIL |
| I6 | `terminal_info().trade_allowed` (Algo Trading) | `False` | WARN only |

Missing field / `None` / wrong type → `UNKNOWN` → stop and ask the user.
Exit codes: `0` PASS (warnings allowed), `2` FAIL, `3` UNKNOWN, `4` config error, `5` initialize failed,
`6` symbol not found / not visible in Market Watch (D-MW; `symbol_select` is never used).
`extract` re-runs these checks on the same connection and reads nothing else if they do not pass.

## Secondary boundaries (code level — not sufficient alone)
4. `MetaTrader5` is imported only in `bridge/mt5_readonly.py`; `ReadOnlyMT5` exposes only the whitelist.
5. `tests/test_no_trade_calls.py` (AST scan of `src/`) fails on: any `order_*` / `orders_*` / `positions_get`
   / `history_orders_*` / `market_book_*` / `symbol_select` / `TRADE_ACTION*` / `ORDER_TYPE*` reference
   (attribute, name, import, string), any `.login(...)` call, `initialize()` with positional args,
   `**kwargs` or any keyword other than `path`, and `MetaTrader5` imports outside the bridge.
   Negative tests prove each pattern is detected.
6. No network server in Phase 0.
7. Account numbers masked (`****1234`) in reports and console output; balance/equity/name not recorded.
   Deal history (D-COMM, D-COMM2) — fields read in memory, nothing else:
   `symbol`, `type`, `entry`, `volume`, `commission`, `fee` (if present), `position_id` (grouping only),
   `time` (only for the first/last deal day). Stored: commission/fee/total aggregates, counts, first/last
   deal day, and a type → count table of deals without a symbol. Never stored: ticket, order, price,
   profit, swap, position id, amounts of non-symbol deals, per-deal rows or timestamp lists.
8. No MQL5 scripts/EAs, no terminal setting changes (Market Watch included).

## Data egress (§4)
- Phase 0: nothing leaves the machine. No AI call. Exception, opt-in only: `ntp_probe = true` makes
  `w32tm /stripchart` query `time.windows.com` (an NTP request, no Aurvex data sent). Default false.
- Phase 1+ (O6, pending): see spec §4 — crop-only chart, structural results; never account number,
  server, balances, positions, credentials, dollar/lot/P&L values; every send logged in `egress_log`.
