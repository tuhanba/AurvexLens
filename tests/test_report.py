"""A6/A7/A8 — end-to-end report on SYNTHETIC — NOT MARKET DATA."""

from __future__ import annotations

import json

import pytest

from aurvex_lens.cli import cmd_extract
from aurvex_lens.common.provenance import sha256_file
from aurvex_lens.data.snapshot import latest_snapshot
from aurvex_lens.quality.report import build_report
from aurvex_lens.quality.result import UNAPPROVED_TZ_LABEL
from tests.conftest import THRESHOLDS
from tests.fixtures.synthetic.fake_mt5 import FakeMT5

CONFIRMED = ('closures = ["Sat 00:00 -> Mon 01:00", "Tue 00:00 -> Tue 01:00", "Wed 00:00 -> Wed 01:00", '
             '"Thu 00:00 -> Thu 01:00", "Fri 00:00 -> Fri 01:00"]\nholiday_dates = ["2026-04-03"]\n'
             'server_time_rule = "US_DST+2"')


def _report(cfg):
    assert cmd_extract(cfg, backend=FakeMT5(), data_origin="SYNTHETIC", sleep=lambda s: None) == 0
    out = build_report(latest_snapshot(cfg.data_dir), cfg, THRESHOLDS)
    return out, json.loads((out / "report.json").read_text(encoding="utf-8")), (out / "report.md").read_text(
        encoding="utf-8")


def _crit(doc, cid):
    return next(c for c in doc["criteria"] if c["id"] == cid)


@pytest.fixture
def unconfirmed(make_cfg):
    return _report(make_cfg())


def test_header(unconfirmed):
    _, doc, md = unconfirmed
    h = doc["header"]
    assert h["data_label"] == "SYNTHETIC — NOT MARKET DATA"
    assert h["thresholds_sha256"] == sha256_file(THRESHOLDS)
    assert h["NEWS_CALENDAR"] == "NOT_CONNECTED"
    assert h["terminal_build"] == 5000 and h["extraction_id"]
    assert "SYNTHETIC — NOT MARKET DATA" in md and "CANLI VERİ" not in md
    assert "NEWS_CALENDAR: NOT_CONNECTED" in md
    assert "PROPOSED" in h["thresholds_status"]


def test_each_criterion_separate_no_score(unconfirmed):
    _, doc, md = unconfirmed
    ids = [c["id"] for c in doc["criteria"]]
    assert ids == ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]
    for c in doc["criteria"]:
        assert c["result"] in ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE_MARKET_CLOSED")
        assert c["method"]
    for cid in ("C1", "C2", "C3", "C4", "C5", "C6"):
        assert _crit(doc, cid)["evidence"], cid
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    assert not [k for k in keys(doc) if "score" in k.lower()]


def test_expected_results_unconfirmed(unconfirmed):
    _, doc, md = unconfirmed
    assert _crit(doc, "C1")["result"] == "FAIL"  # ~7 weeks < 24 months
    assert _crit(doc, "C2")["result"] == "FAIL"  # 45-min unexplained gap > 30 min
    assert _crit(doc, "C3")["result"] == "UNKNOWN"  # O3 not approved
    assert _crit(doc, "C4")["result"] == "UNKNOWN"
    assert _crit(doc, "C5")["result"] == "FAIL"  # commission/contract not verified
    assert _crit(doc, "C6")["result"] == "PASS"  # synthetic bars are built from bid
    c7 = _crit(doc, "C7")
    assert c7["result"] == "FAIL" and c7["metrics"]["NEWS_CALENDAR"] == "NOT_CONNECTED"
    assert UNAPPROVED_TZ_LABEL in md  # A8: UTC-derived tables labelled


def test_c4_ranks_true_rule_first(unconfirmed):
    _, doc, _ = unconfirmed
    rows = _crit(doc, "C4")["tables"][0]["rows"]
    assert rows[0]["rule"] == "US_DST+2"
    assert rows[0]["unexplained"] == 1  # Good Friday week


def test_c5_bar_spread_mapping(unconfirmed):
    _, doc, _ = unconfirmed
    m = _crit(doc, "C5")["metrics"]
    assert m["bar_spread_mapping"]["best_matching_statistic"] == "open"
    assert m["spread_ticks"]["status"] == "SINGLE_SOURCE"
    assert m["slippage"]["status"] == "MISSING"
    assert m["commission"]["status"] == "MISSING"


def test_confirmed_closures_and_rule(make_cfg):
    _, doc, md = _report(make_cfg(confirmations=CONFIRMED))
    c2 = _crit(doc, "C2")
    m1 = next(s for s in c2["sub_results"] if s.get("timeframe") == "M1")
    assert m1["unconfirmed_closure_or_holiday_gaps"] == 0 and m1["result"] == "FAIL"
    h1 = next(s for s in c2["sub_results"] if s.get("timeframe") == "H1")
    assert h1["result"] == "PASS"
    c4 = _crit(doc, "C4")
    rule_sub = next(s for s in c4["sub_results"] if s["check"] == "approved_rule_unexplained_weeks")
    assert rule_sub["value"] == 0 and rule_sub["result"] == "PASS"
    assert c4["result"] == "UNKNOWN"  # local clock status unknown off-Windows
    assert doc["header"]["server_time_rule"] == "US_DST+2"
    assert UNAPPROVED_TZ_LABEL not in md
