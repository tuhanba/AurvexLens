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
