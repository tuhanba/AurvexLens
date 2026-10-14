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
| O2 | OPEN | Data suitability thresholds (incl. `commission_match_tolerance`, `c6_min_bid_match_ratio`, `closure_min_recurrence`). | All marked PROPOSED; approval = sha256 in `local.toml`. |
| O3 | OPEN | Broker server-time rule and historical DST mapping. | C4 shows candidate rules (NY + UTC frames); no `time_utc` until approved; never auto-approved. |
| O4 | OPEN | Economic calendar source. | C7 = `NOT_CONNECTED`; "news check not done". |
| O5 | OPEN | First strategy + pre-registration protocol. | Out of scope. |
| O6 | OPEN | What data may go to the AI; dollar values never sent (placeholders). | No egress in Phase 0. |
| O7 | OPEN | Remote access from phone. | No server; 127.0.0.1 only later. |
| O8 | OPEN | Reuse of the existing collector. | Not touched; no decision without inspecting files. |
| O9 | OPEN | Threshold for cross-timeframe consistency (M1 resampled vs terminal M5/M15/H1). | Phase 0 reports only. Must be fixed before Phase 1 **without looking at the results**. |

## KARAR — 2026-10-14, kullanıcı onaylı

| ID | Decision | Implementation |
|---|---|---|
| D-I1 | Path comparison: `terminal_info().path` vs folder of configured exe; both sides `normcase(normpath())`. `forbidden_terminal_paths` uses the same normalization. | `common/config.py` uses `ntpath` (= `os.path` on Windows) so Linux CI behaves like Windows. Tests: slash direction, trailing separator, case, `.` segments. |
| D-C4 | `reference_tz = "America/New_York"` default. Report shows candidate rules in NY and UTC frames side by side. Rule selection is never auto-approved; O3 stays a user approval. | `quality/server_time.py` evaluates both frames; result uses the reference frame. |
| D-NFP | First-Friday approximation is never PASS evidence. Official BLS calendar via `nfp_calendar_path` (CSV `date,release_time_et`, user-supplied). Missing file → NFP check UNKNOWN. Approximate analysis shown only as "approx — not evidence" and never affects C4. | NFP is reported as a non-gating evidence sub-check; ranking uses official hits only. |
| D-TICK | Tick probe: first Wednesday of each month 14:00–15:00 server time; if empty, the next 4 business days. Statuses `TICKS_FOUND` / `WINDOW_EMPTY_RETRIED` / `NO_HISTORY_BEFORE`. | `data/extract.py` `probe_ticks`. |
| D-SAFE | Forbidden list confirmed: `order_send`, `order_check`, `order_calc_*`, `positions_get`, `orders_get`, `symbol_select`, `.login()`. `test_no_trade_calls.py` is not weakened. | Unchanged. |
| D-P07 | Spec P0.7: `positions_get` → `positions_total` (spec inconsistency). | `docs/03_phase0_spec.md` corrected. |
| D-COMM | Commission reading approved, aggregates only. `history_deals_get` over `commission_history_days = 180`; in memory only `symbol, volume, entry, commission, position_id` (+ deal time for first/last day). Per-side per-lot (IN/OUT: median, min, max, n) and round-turn per lot by position (IN+OUT / volume). Only aggregates + first/last deal day are stored. No deals → `MISSING/NO_DEALS`; history not returned → `MISSING/ACCESS_DENIED`. VERIFIED if round-turn median matches official value (with source URL + date) within `commission_match_tolerance = 0.01` (PROPOSED); mismatch → CONFLICT; one source → SINGLE_SOURCE. | `data/commission.py`, `quality/costs.py`; test asserts no per-deal values in snapshot/report/stdout. |
| D-C7 | C7 result is `NOT_CONNECTED`, not FAIL; never counts as PASS. | `quality/result.py` (`NOT_CONNECTED`, `is_pass`, `data_gate`); report header shows `phase1_data_gate`. |
| D-C5 | `CONFLICT` status accepted. | — |
| D-THR | `c6_min_bid_match_ratio = 0.999` and `closure_min_recurrence = 8` kept, marked PROPOSED. Cross-TF consistency: report only in Phase 0 (threshold → O9). | Config comments. |
| D-NTP | `w32tm /query /status` stays (localized → UNKNOWN + raw text kept). Optional `w32tm /stripchart /computer:time.windows.com /samples:3 /dataonly` for numeric offset — external NTP query, config `ntp_probe = false` by default; when false it never runs. Report states which method was used. | `data/extract.py` `windows_clock_status`. |
| D-MW | `symbol_info()` None or `visible == False` → FAIL with "Sembol Market Watch'ta görünmüyor — terminalde elle ekleyin." `symbol_select` not used. | `extract` exits with code 6; aborted snapshot is kept as evidence but never reported on. |
| D-C4G | C4 gating: sub-check `approved_rule_matches_live_offset` (PASS if the approved rule's offset equals the live offset, FAIL if not, UNKNOWN if the live offset is not MEASURED) is part of `combine()`. If the official NFP calendar is LOADED and the approved rule's official NFP hits are not the highest among candidates → gating sub-check `nfp_official_conflict = UNKNOWN`. Without a calendar this sub-check is not added (NFP alone is never PASS evidence). | `quality/server_time.py`. Live offset is MEASURED only if the tick time changed during the probe (else `STALE_TICKS`); the freshest sample is rounded to 15 min. |
| D-COMM2 | Commission measurement: only `DEAL_TYPE_BUY/SELL` (type 0/1) deals enter statistics (others counted). `fee` read if present; commission = commission + fee, reported as separate `commission` / `fee` / `total` statistics; missing field → fee component MISSING. Positions containing an `ENTRY_INOUT` or `ENTRY_OUT_BY` deal are excluded from round turn (count reported). All measured commission+fee = 0 → `SUSPECT_ZERO` (never VERIFIED/PASS), with a type → count table of symbol-less deals (no amounts, tickets or times). Comparison stays on absolute values, but a broker median > 0 → `CONFLICT` (`positive_commission_from_broker`). | `data/commission.py`, `quality/costs.py`. |
| D-DOC | docs/01 lists the deal fields read (`time` only for first/last day, `type`, `fee`); README has an exit-code table incl. 6. | — |

