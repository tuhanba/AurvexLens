# 02 — Data suitability criteria (Phase 0 implementation)

Source: `docs/03_phase0_spec.md` §6. No aggregate quality score. Each criterion returns PASS / FAIL /
UNKNOWN independently (C3 may also return `NOT_APPLICABLE_MARKET_CLOSED`, C7 returns `NOT_CONNECTED`);
only PASS passes. The report header shows `phase1_data_gate` (any blocking criterion not PASS → DATA_INSUFFICIENT).
Thresholds: `config/quality_thresholds.toml` (PROPOSED until the user records its sha256 in
`config/local.toml [confirmations].thresholds_approved_sha256`).

All bar/tick times are **broker server time** (`time_server`), not UTC.

## What `extract` stores (`data/raw/<extraction_id>/`)
| File | Content |
|---|---|
| `identity.json` | identity result of this connection |
| `symbol_snapshot.json` | full `symbol_info` dump, `symbols_get("*XAG*")` names, Market Watch visibility, tick at snapshot (P0.4). Not found / not visible → extract FAIL (exit 6), nothing else read |
| `clock_status.json` | `w32tm /query /status` output + parse; optional `w32tm /stripchart` offsets if `ntp_probe = true`; `methods_used` |
| `live_probe.json` | N × (system UTC ms, last tick time_msc, bid/ask, `connected`), 1 s apart (C3/C4) |
| `rates_<TF>.parquet` | `copy_rates_from_pos` paged from pos 0 back to the oldest bar (P0.5) |
| `tick_probes.json` / `ticks_probe.parquet` | monthly 1 h tick probes with retries and per-month status (C1 tick coverage) |
| `ticks_recent.parquet` | full ticks of the last `tick_full_days` server days (C5/C6) |
| `access_probe.json` | deal count, deal field names, commission **aggregates** (D-COMM), `positions_total` (P0.7) |
| `meta.json` | ids, UTC extraction time, terminal build, package versions, per-file sha256/rows/range |

Files are created with exclusive mode, set read-only, and re-hashed by `report` before use.

## Methods
- **C1** — per TF first/last bar, span (days / 30.4375 = months) vs threshold. Expected bars =
  rows + missing slots outside closures (confirmed or candidate). If rows ≥ terminal `maxbars`, flagged as
  possibly truncated by the terminal setting. Ticks (D-TICK): first Wednesday of each month 14:00–15:00 server,
  if empty the next 4 business days; month status `TICKS_FOUND` / `WINDOW_EMPTY_RETRIED` (empty after
  retries, newer than the oldest data) / `NO_HISTORY_BEFORE` (empty and older than the oldest month with ticks);
  stops after 3 consecutive empty months once data was found (±1 month resolution); no threshold.
- **C2** — gap = consecutive bars further apart than one TF. Every missing slot `[t, t+TF)` is tested
  against weekly closure intervals in server time. Closure candidates = `(start, end)` week-minute
  patterns of the finest TF recurring ≥ `closure_min_recurrence` times. Classes:
  `EXPECTED_CLOSURE` (all slots inside user-confirmed closures, or extra slots only on confirmed holiday
  dates), `CLOSURE_CANDIDATE` (inside candidates, unconfirmed), `HOLIDAY_CANDIDATE` (touches a closure
  and extends beyond it — early close / late open / full-day closure), `UNEXPLAINED` (everything else —
  only these count as outages). Per TF: unexplained ratio, longest unexplained gap, duration buckets.
  Cross-TF: M1 resampled to M5/M15/H1 vs terminal OHLC and tick volume (reported; a threshold exists
  only if the user enables `extra.cross_tf_max_price_mismatch_ratio`).
- **C3** — needs approved server-time rule (else UNKNOWN). Tick age = system UTC − (tick server time −
  rule offset). Market state from confirmed closures; closed → `NOT_APPLICABLE_MARKET_CLOSED`.
  `connected == False` in any sample → FAIL. Normal tick frequency = inter-tick intervals < 300 s.
- **C4** — local clock from `w32tm /query /status` (unparseable/localized output → UNKNOWN, raw text kept);
  optional numeric offset via `w32tm /stripchart` only if `ntp_probe = true` (reported, not gating).
  Current offset = median(tick server time − system UTC), rounded to 15 min. Candidate rules
  `FIXED+k`, `EU_DST+k` (Europe/London switches), `US_DST+k` (America/New_York switches),
  k ∈ `server_rule_base_offsets`. Anchors from the M5 gaps (weekly open/close, daily break) are converted
  server → UTC → frame; a week matches a rule if every anchor equals that rule's modal frame time.
  Reference frame America/New_York (D-C4), UTC shown side by side. US/EU DST divergence weeks counted
  separately. NFP (D-NFP): max-range bar on each official BLS release date (user CSV) should start at the
  release minute ET; no calendar → UNKNOWN; first-Friday approximation shown as "approx — not evidence"
  and never used for ranking or result. Anchors alone cannot identify the base offset k inside a DST family;
  the official NFP hits and the live offset do. PASS needs an approved rule (O3) with 0 unexplained weeks
  (confirmed-holiday weeks excluded) and a synced local clock. Week matrix: `c4_rule_match_weeks.csv`.
- **C5** — status per component: `VERIFIED` / `SINGLE_SOURCE` / `MISSING` / `CONFLICT`
  (two sources disagree). Spread from tick bid/ask by server hour (single feed → SINGLE_SOURCE).
  Bar spread vs per-bar tick min/mean/open/close/max (match = |diff| ≤ 0.5 point); bar spread stays
  "indicative". Commission (D-COMM): deal aggregates (per side IN/OUT and round turn per lot) vs official
  value with source URL + verification date; |median| vs |official| within `commission_match_tolerance` →
  VERIFIED, else CONFLICT; one source → SINGLE_SOURCE; no deals → MISSING/NO_DEALS; history not returned →
  MISSING/ACCESS_DENIED. Swap / contract: `symbol_info` vs official values in config. Slippage: MISSING.
- **C6** (informational, non-blocking) — M1 OHLC vs tick-derived bid and ask OHLC per minute.
- **C7** — calendar not connected → `NOT_CONNECTED` (D-C7); never PASS.

## Remaining implementation notes
1. Commission comparison uses absolute values (brokers report commission as a negative charge).
2. Round turn counts only positions fully closed inside the window (IN volume == OUT volume).
3. Deal `time` is read in memory only to report the first/last deal day (server date).
4. NFP is evidence only (non-gating): the spec's C4 threshold (§6.2) does not include it.
5. The `ntp_probe` offset is reported; no threshold exists for it, so it does not decide `local_clock_synced`.
