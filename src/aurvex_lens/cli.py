"""aurvex-lens identity | extract | report

identity / extract connect to the configured (separate, investor-logged-in)
MT5 terminal. report works offline on a finalized snapshot.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from aurvex_lens.bridge.identity import EXIT_CONFIG, EXIT_INIT, EXIT_OK, IdentityReport, verify_identity
from aurvex_lens.bridge.mt5_readonly import ReadOnlyMT5
from aurvex_lens.common.config import DEFAULT_CONFIG, DEFAULT_THRESHOLDS, ConfigError, LensConfig, load_config
from aurvex_lens.common.provenance import dumps, new_run_id
from aurvex_lens.data.extract import run_extraction
from aurvex_lens.data.snapshot import ORIGIN_LIVE, latest_snapshot
from aurvex_lens.quality.report import ReportError, build_report


def _print_identity(rep: IdentityReport) -> None:
    print(f"identity: {rep.overall} (exit {rep.exit_code})")
    for c in rep.checks:
        print(f"  [{c.result:7}] {c.id}: observed={c.observed!r} expected={c.expected!r} {c.note}")
    if rep.init_error is not None:
        print(f"  initialize() failed: last_error={rep.init_error!r}")


def _write_identity(cfg: LensConfig, rep: IdentityReport) -> Path:
    d = cfg.data_dir / "reports" / "identity" / new_run_id("identity_")
    d.mkdir(parents=True, exist_ok=False)
    p = d / "identity_report.json"
    p.write_text(dumps(rep.to_dict()), encoding="utf-8")
    return p


def cmd_identity(cfg: LensConfig, backend: Any = None) -> int:
    mt5 = ReadOnlyMT5(backend)
    rep = verify_identity(mt5, cfg)
    try:
        path = _write_identity(cfg, rep)
    finally:
        if rep.initialized:
            mt5.shutdown()
    _print_identity(rep)
    print(f"identity_report: {path}")
    return rep.exit_code


def cmd_extract(cfg: LensConfig, backend: Any = None, data_origin: str = ORIGIN_LIVE, **kw: Any) -> int:
    mt5 = ReadOnlyMT5(backend)
    rep = verify_identity(mt5, cfg)
    try:
        path = _write_identity(cfg, rep)
        _print_identity(rep)
        print(f"identity_report: {path}")
        if rep.exit_code != EXIT_OK:
            print("extract aborted: identity not PASS — no data was read.")
            return rep.exit_code
        writer = run_extraction(mt5, cfg, rep.to_dict(), new_run_id(), data_origin, **kw)
    finally:
        if rep.initialized:
            mt5.shutdown()
    print(f"snapshot: {writer.dir}")
    for f in writer.files:
        print(f"  {f['file']}: rows={f.get('rows', '-')} sha256={f['sha256'][:16]}…")
    return EXIT_OK


def cmd_report(cfg: LensConfig, extraction_id: str | None, thresholds: Path) -> int:
    snap = (cfg.data_dir / "raw" / extraction_id) if extraction_id else latest_snapshot(cfg.data_dir)
    out = build_report(snap, cfg, thresholds)
    print(f"report: {out / 'report.md'}")
    print(f"report: {out / 'report.json'}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="aurvex-lens", description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("identity", help="verify terminal/account identity (no market data read)")
    sub.add_parser("extract", help="identity check, then raw snapshot extraction")
    r = sub.add_parser("report", help="offline data suitability report from a snapshot")
    r.add_argument("--extraction-id", default=None, help="default: latest snapshot")
    r.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return EXIT_CONFIG
    try:
        if args.cmd == "identity":
            return cmd_identity(cfg)
        if args.cmd == "extract":
            return cmd_extract(cfg)
    except ModuleNotFoundError as e:
        print(f"MetaTrader5 package not available ({e}); live commands need Windows + MetaTrader5.",
              file=sys.stderr)
        return EXIT_INIT
    try:
        return cmd_report(cfg, args.extraction_id, args.thresholds)
    except ReportError as e:
        print(f"report error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
