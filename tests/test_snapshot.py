"""A5 — immutable snapshots (SYNTHETIC — NOT MARKET DATA)."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from aurvex_lens.cli import cmd_extract
from aurvex_lens.common.provenance import sha256_file
from aurvex_lens.data.snapshot import SnapshotWriter, verify_snapshot
from tests.fixtures.synthetic.fake_mt5 import FakeMT5


def _extract(cfg):
    fake = FakeMT5()
    assert cmd_extract(cfg, backend=fake, data_origin="SYNTHETIC", sleep=lambda s: None) == 0
    return fake


def test_extract_writes_snapshot_with_meta(make_cfg):
    cfg = make_cfg()
    fake = _extract(cfg)
    assert "initialize" in fake.calls and fake.calls[-1] == "shutdown"
    dirs = list((cfg.data_dir / "raw").iterdir())
    assert len(dirs) == 1
    meta = json.loads((dirs[0] / "meta.json").read_text(encoding="utf-8"))
    assert meta["data_origin"] == "SYNTHETIC"
    for k in ("extraction_id", "extraction_started_utc", "terminal_build", "versions", "symbol"):
        assert k in meta
    names = {f["file"] for f in meta["files"]}
    for tf in ("H1", "M15", "M5", "M1"):
        assert f"rates_{tf}.parquet" in names
    for e in meta["files"]:
        assert sha256_file(dirs[0] / e["file"]) == e["sha256"]
        if e["file"].startswith("rates_"):
            for k in ("timeframe", "requested_range", "rows", "first_time_server", "last_time_server"):
                assert k in e
    h1 = pd.read_parquet(dirs[0] / "rates_H1.parquet")
    assert "time_server" in h1.columns and "time" not in h1.columns and "time_utc" not in h1.columns
    assert h1["time_server"].is_monotonic_increasing and h1["time_server"].is_unique
    sym = json.loads((dirs[0] / "symbol_snapshot.json").read_text(encoding="utf-8"))
    assert sym["matching_symbol_names"] == ["XAGUSD", "XAGEUR"]
    acc = json.loads((dirs[0] / "access_probe.json").read_text(encoding="utf-8"))
    assert acc["deal_field_names"] and "price" not in json.dumps({k: v for k, v in acc.items()
                                                                  if k != "deal_field_names"})


def test_paging_reaches_oldest_bar(make_cfg):
    from tests.fixtures.synthetic import synth
    cfg = make_cfg()
    _extract(cfg)
    d = next((cfg.data_dir / "raw").iterdir())
    m1 = pd.read_parquet(d / "rates_M1.parquet")
    assert len(m1) == len(synth.m1())  # 46875 rows > rates_chunk 20000 -> multiple pages


def test_second_run_new_folder_old_unchanged(make_cfg):
    cfg = make_cfg()
    _extract(cfg)
    first = next((cfg.data_dir / "raw").iterdir())
    before = {p.name: sha256_file(p) for p in first.iterdir()}
    _extract(cfg)
    dirs = sorted((cfg.data_dir / "raw").iterdir())
    assert len(dirs) == 2
    assert {p.name: sha256_file(p) for p in first.iterdir()} == before
    assert all(x["ok"] for x in verify_snapshot(first))


def test_writer_refuses_overwrite(tmp_path):
    w = SnapshotWriter(tmp_path, "x1", "SYNTHETIC")
    w.write_json("a.json", {"a": 1})
    with pytest.raises(FileExistsError):
        w.write_json("a.json", {"a": 2})
    with pytest.raises(FileExistsError):
        SnapshotWriter(tmp_path, "x1", "SYNTHETIC")


def test_tamper_detected(make_cfg):
    import os
    import stat
    cfg = make_cfg()
    _extract(cfg)
    d = next((cfg.data_dir / "raw").iterdir())
    p = d / "live_probe.json"
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    p.write_text("{}")
    assert not all(x["ok"] for x in verify_snapshot(d))


@pytest.mark.parametrize("fake_kw,cfg_kw", [({"symbol_visible": False}, {}), ({}, {"symbol": "XAGUSD."})])
def test_symbol_not_in_market_watch_fails(make_cfg, capsys, fake_kw, cfg_kw):
    cfg = make_cfg(**cfg_kw)
    fake = FakeMT5(**fake_kw)
    rc = cmd_extract(cfg, backend=fake, data_origin="SYNTHETIC", sleep=lambda s: None)
    assert rc == 6
    assert "Sembol Market Watch'ta görünmüyor — terminalde elle ekleyin." in capsys.readouterr().out
    assert "copy_rates_from_pos" not in fake.calls and "copy_ticks_range" not in fake.calls
    assert not hasattr(fake, "symbol_select")
    from aurvex_lens.data.snapshot import SnapshotError, latest_snapshot
    with pytest.raises(SnapshotError):
        latest_snapshot(cfg.data_dir)  # aborted snapshots are never reported on


def test_tick_probe_statuses():
    import calendar
    from aurvex_lens.data.extract import NO_HISTORY_BEFORE, TICKS_FOUND, WINDOW_EMPTY_RETRIED, probe_ticks
    from aurvex_lens.bridge.mt5_readonly import ReadOnlyMT5
    from tests.fixtures.synthetic import synth
    latest = int(synth.ticks()["time"].iloc[-1])
    _, probes = probe_ticks(ReadOnlyMT5(FakeMT5()), "XAGUSD", latest, 12, 3)
    st = {p["month"]: p for p in probes}
    assert st["2026-04"]["status"] == TICKS_FOUND and not st["2026-04"]["retry_used"]
    assert st["2026-03"]["status"] == TICKS_FOUND
    assert st["2026-02"]["status"] == NO_HISTORY_BEFORE  # synthetic data starts 2026-02-23
    assert len(st["2026-02"]["attempts"]) == 5  # first Wednesday + 4 business days
    days = [calendar.weekday(*__import__("time").gmtime(a["window_start_server"])[:3])
            for a in st["2026-02"]["attempts"]]
    assert days == [2, 3, 4, 0, 1]  # Wed Thu Fri Mon Tue
    assert WINDOW_EMPTY_RETRIED not in {p["status"] for p in probes}


def test_tick_probe_retry_finds_later_day():
    from aurvex_lens.data.extract import TICKS_FOUND, probe_ticks
    from aurvex_lens.bridge.mt5_readonly import ReadOnlyMT5

    class GapFake(FakeMT5):
        def copy_ticks_range(self, symbol, a, b, flags):  # first Wednesday of March 2026 is empty
            if int(a.timestamp()) == 1772632800:
                return super().copy_ticks_range(symbol, a, a, flags)[:0]
            return super().copy_ticks_range(symbol, a, b, flags)
    from tests.fixtures.synthetic import synth
    _, probes = probe_ticks(ReadOnlyMT5(GapFake()), "XAGUSD", int(synth.ticks()["time"].iloc[-1]), 12, 3)
    mar = next(p for p in probes if p["month"] == "2026-03")
    assert mar["status"] == TICKS_FOUND and mar["retry_used"] and len(mar["attempts"]) == 2


def test_ntp_probe_disabled_never_runs():
    from aurvex_lens.data.extract import windows_clock_status
    cmds = []
    out = windows_clock_status(lambda c: cmds.append(c) or "Leap Indicator: 0(no warning)\nSource: time.windows.com\n",
                               ntp_probe=False)
    assert cmds == [["w32tm", "/query", "/status"]]
    assert out["status"] == "SYNCED" and out["ntp_probe"].startswith("DISABLED")


def test_ntp_probe_enabled_parses_offsets():
    from aurvex_lens.data.extract import windows_clock_status
    strip = "12:00:01, +00.0123456s\n12:00:03, -00.0023456s\n12:00:05, +00.0050000s\n"
    out = windows_clock_status(lambda c: strip if "/stripchart" in c else "Kaynak: x\n", ntp_probe=True)
    assert out["status"] == "UNKNOWN"  # localized /query output stays UNKNOWN, raw kept
    assert out["raw"] == "Kaynak: x\n"
    assert out["ntp_probe"]["offsets_s"] == [0.0123456, -0.0023456, 0.005]
    assert len(out["methods_used"]) == 2
