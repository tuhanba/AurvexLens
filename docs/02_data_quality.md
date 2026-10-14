# 02 — Data suitability criteria (Phase 0 implementation)

Source: `docs/03_phase0_spec.md` §6. No aggregate quality score. Each criterion returns PASS / FAIL /
UNKNOWN independently (C3 may also return `NOT_APPLICABLE_MARKET_CLOSED`); UNKNOWN is never PASS.
Thresholds: `config/quality_thresholds.toml` (PROPOSED until the user records its sha256 in
`config/local.toml [confirmations].thresholds_approved_sha256`).

All bar/tick times are **broker server time** (`time_server`), not UTC.

## What `extract` stores (`data/raw/<extraction_id>/`)
| File | Content |
|---|---|
| `identity.json` | identity result of this connection |
| `symbol_snapshot.json` | full `symbol_info` dump, `symbols_get("*XAG*")` names, tick at snapshot (P0.4) |
| `clock_status.json` | `w32tm /query /status` output + parse (C4 local clock) |
| `live_probe.json` | N × (system UTC ms, last tick time_msc, bid/ask, `connected`), 1 s apart (C3/C4) |
| `rates_<TF>.parquet` | `copy_rates_from_pos` paged from pos 0 back to the oldest bar (P0.5) |
| `tick_probes.json` / `ticks_probe.parquet` | monthly 1 h tick probes (C1 tick coverage) |
| `ticks_recent.parquet` | full ticks of the last `tick_full_days` server days (C5/C6) |
| `access_probe.json` | deal count, deal field names, commission-field presence, `positions_total` (P0.7) |
| `meta.json` | ids, UTC extraction time, terminal build, package versions, per-file sha256/rows/range |

Files are created with exclusive mode, set read-only, and re-hashed by `report` before use.

## Methods
- **C1** — per TF first/last bar, span (days / 30.4375 = months) vs threshold. Expected bars =
  rows + missing slots outside closures (confirmed or candidate). If rows ≥ terminal `maxbars`, flagged as
  possibly truncated by the terminal setting. Ticks: first Wednesday of each month, 14:00–15:00 server,
  going back until 3 consecutive empty months after data was found (±1 month resolution); no threshold.
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
- **C4** — local clock from `w32tm` (unparseable/localized output → UNKNOWN, raw text kept).
  Current offset = median(tick server time − system UTC), rounded to 15 min. Candidate rules
  `FIXED+k`, `EU_DST+k` (Europe/London switches), `US_DST+k` (America/New_York switches),
  k ∈ `server_rule_base_offsets`. Anchors from the M5 gaps (weekly open/close, daily break) are converted
  server → UTC → **reference frame** (`analysis.reference_tz`, default America/New_York); a week matches a
  rule if every anchor equals that rule's modal frame time. US/EU DST divergence weeks counted separately.
  NFP check: max-range bar on the first Friday of each month should start at 08:30 New York.
  PASS needs an approved rule with 0 unexplained weeks (weeks with confirmed holidays excluded) and a
  synced local clock. Week-level matrix: `c4_rule_match_weeks.csv`.
- **C5** — status per component: `VERIFIED` / `SINGLE_SOURCE` / `MISSING` / `CONFLICT`
  (two sources disagree). Spread from tick bid/ask by server hour (single feed → SINGLE_SOURCE).
  Bar spread vs per-bar tick min/mean/open/close/max (match = |diff| ≤ 0.5 point); bar spread stays
  "indicative". Commission: official value from config; deal values are not read in Phase 0 (P0.7), so it
  cannot reach VERIFIED yet. Swap / contract: `symbol_info` vs official values in config. Slippage: MISSING.
- **C6** (informational, non-blocking) — M1 OHLC vs tick-derived bid and ask OHLC per minute.
- **C7** — calendar not connected → FAIL with `NEWS_CALENDAR: NOT_CONNECTED`.

## Implementation assumptions (need user confirmation)
1. `terminal_info().path` is a folder; `terminal_path` is the `.exe`. I1 compares the exe's folder.
2. Reference frame for C4 is America/New_York (silver sessions follow New York time). The spec wording
   says "UTC"; in a UTC frame a NY-anchored session moves with US DST, so a fixed-offset rule would wrongly
   look constant. Set `reference_tz = "UTC"` to use the spec's literal frame.
3. NFP dates approximated as first Friday of the month (not the official BLS calendar).
4. Tick probe window = first Wednesday 14:00–15:00 server (spec example "start of each month" often falls
   on weekends/holidays).
5. `CONFLICT` status added to C5; C7 without a calendar is reported as FAIL.
6. `extra.c6_min_bid_match_ratio` (0.999) is not in spec §6.2 — added, needs approval.
7. P0.7: whitelist contains `positions_total`, not `positions_get`; only the count is recorded.
