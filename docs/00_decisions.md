# 00 — Decisions (ADR log)

Source: `docs/03_phase0_spec.md` §2. Format: ID · status · decision · consequence.
Records are append-only: a changed decision gets a new entry that supersedes the old one.

## Accepted

| ID | Status | Decision | Consequence |
|---|---|---|---|
| D1 | ACCEPTED | Product flow: upload chart → confirm inputs → analysis → conditional plan → outcome tracking. Measurement infrastructure is the backbone, not the product. | Phase 0 builds measurement only. |
| D2 | ACCEPTED | Local on Windows; Python engine; local data bridge; mobile-friendly web UI (Phase 1+). | No server in Phase 0. |
| D3 | ACCEPTED | No orders, ever (open/modify/close). | Static safety test; read-only whitelist. |
| D4 | ACCEPTED | First instrument XAGUSD; screenshots from MT5. TradingView out of scope (v1). | Symbol name confirmed by user (P6). |
| D5 | ACCEPTED | Existing EA terminal/account/settings untouched; never connected to. | `forbidden_terminal_paths`, checked before `initialize()`. |
| D6 | ACCEPTED | Plan states are distinct (spec §2.3); never merged into an unexplained "WAIT". | Phase 1. |
| D7 | ACCEPTED | Plan records append-only; revision = new record. | Phase 1. |
| D8 | ACCEPTED | Simulated results and real trades in separate tables. | Phase 1. |
| D9 | ACCEPTED | FTMO rules only from official FTMO source + user account info, versioned (URL, verification date, product, phase). | `docs/rules/` (schema only in Phase 0). |
| D10 | ACCEPTED (hypothesis) | Start timeframes H1 context / M15 structure / M5 entry, 30–120 min horizon — a hypothesis to test, not a proven optimum. | Phase 0 extracts H1/M15/M5/M1. |

## Open

| ID | Status | Question | Phase 0 handling |
|---|---|---|---|
| O1 | OPEN | Is separate terminal + investor access workable? | `identity` records observed field behaviour (P0.3). |
| O2 | OPEN | Data suitability thresholds. | `config/quality_thresholds.toml` marked PROPOSED; approval = sha256 in `local.toml`. |
| O3 | OPEN | Broker server-time rule and historical DST mapping. | C4 ranks candidate rules; no `time_utc` until approved. |
| O4 | OPEN | Economic calendar source. | `NEWS_CALENDAR: NOT_CONNECTED`; "news check not done". |
| O5 | OPEN | First strategy + pre-registration protocol. | Out of scope. |
| O6 | OPEN | What data may go to the AI; dollar values never sent (placeholders). | No egress in Phase 0. |
| O7 | OPEN | Remote access from phone. | No server; 127.0.0.1 only later. |
| O8 | OPEN | Reuse of the existing collector. | Not touched; no decision without inspecting files. |
