# Aurvex Lens

Personal decision-support tool for MT5 charts. **It never places, modifies or closes orders.**

This repository currently contains **Phase 0 only**: project skeleton, a read-only MT5 bridge with
identity verification, raw data extraction into immutable snapshots, and a data suitability report
(criteria C1–C7, each PASS / FAIL / UNKNOWN, no aggregate score). Spec: `docs/03_phase0_spec.md`.

## Requirements

- Windows 10/11 x64 (the `MetaTrader5` Python package is Windows-only).
- Python **3.13** x64 (MetaTrader5 5.0.6231 ships wheels for 3.6–3.14; pandas 3.0 / pyarrow 26 need ≥ 3.11;
  pinned to 3.13 as the tested target).
- A **separate** MT5 installation used only by Aurvex Lens (e.g. `C:\AurvexLens\mt5\`), logged in
  **manually with the FTMO investor (read-only) password**. Aurvex Lens never receives a password.
- The symbol (e.g. `XAGUSD`) visible in that terminal's Market Watch (Aurvex Lens does not change Market Watch).

## Install (PowerShell, one command per line)

```
cd C:\AurvexLens
```
```
git clone <repo-url> aurvex-lens
```
```
cd C:\AurvexLens\aurvex-lens
```
```
py -3.13 -m venv .venv
```
```
.\.venv\Scripts\Activate.ps1
```
```
python -m pip install --upgrade pip
```
```
python -m pip install -e ".[dev]"
```

## Configure

```
Copy-Item config\lens.example.toml config\local.toml
```

Edit `config\local.toml` (never committed): `terminal_path` (separate terminal's `terminal64.exe`),
`forbidden_terminal_paths` (the EA terminal), `expected_login`, `expected_server`, symbol name.
No passwords. `config\quality_thresholds.toml` holds the **PROPOSED** thresholds (user approval pending).

## Test (no MT5 needed)

```
python -m pytest
```

## Run (live — only after the prerequisites in docs/03 §1 are confirmed)

Open the separate terminal and log in with the investor password manually first. Then:

```
aurvex-lens identity
```
```
aurvex-lens extract
```
```
aurvex-lens report
```

- `identity` writes `data\reports\identity\<run>\identity_report.json`. Non-zero exit = stop:
  `2` FAIL, `3` UNKNOWN (a field behaved unexpectedly — ask, do not assume), `4` config error,
  `5` `initialize()` failed.
- `extract` repeats the identity check on the same connection and reads market data only if it passes.
  Output: `data\raw\<extraction_id>\` (never overwritten) with `meta.json` + sha256 per file.
- `report` is offline (no MT5). Output: `data\reports\<extraction_id>\<report_run>\report.md` / `report.json`.
  Use `aurvex-lens report --extraction-id <id>` for a specific snapshot.

## After the first live report

Fill `[confirmations]` in `config\local.toml` from what the report shows (closure patterns,
holiday dates, server-time rule, thresholds sha256) and the `[official_costs.*]` sections
from the official FTMO sources, then run `aurvex-lens report` again. Nothing is confirmed automatically.
