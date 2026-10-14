# Aurvex Lens — Claude Code project rules

Full spec: `docs/03_phase0_spec.md`. Decisions: `docs/00_decisions.md`.
Safety: `docs/01_safety_boundaries.md`. Data quality: `docs/02_data_quality.md`.

## Absolute rules
- This project never sends orders. No MT5 call that opens, modifies or closes orders/positions is ever written.
- `MetaTrader5` is imported only in `src/aurvex_lens/bridge/mt5_readonly.py`; only its whitelist is exposed.
- `initialize()` is called only with `path=`; `login` / `password` / `server` parameters are forbidden.
- Never touch the existing EA terminal, its install path or its settings files (nor AurvexAI / collector dirs).
- Synthetic data lives only under `tests/fixtures/synthetic/`; its outputs must carry `SYNTHETIC — NOT MARKET DATA`.
- A value that cannot be measured is reported as `UNKNOWN` / `MISSING`; never filled with an estimate or default.
- `time_server` is not UTC; no UTC label without an approved server-time rule (open decision O3).
- Raw snapshots are never overwritten.
- Account numbers are masked in logs and reports (`****1234`).
- Live MT5 commands are not run unless the user explicitly says "çalıştır" / "canlı çalıştır".
- Phase 0: no MQL5 scripts/EAs, no terminal setting changes (incl. Market Watch `symbol_select`), no network server.

## Working
- Tests: `python -m pytest` — must pass without MT5 (fake MT5 + synthetic fixtures).
- `tests/test_no_trade_calls.py` is the static safety gate; never weaken it to make code pass.
- Open decisions (O1–O8) are asked, not assumed.
