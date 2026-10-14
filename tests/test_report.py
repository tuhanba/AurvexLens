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


def _report(cfg, **fake_kw):
    assert cmd_extract(cfg, backend=FakeMT5(**fake_kw), data_origin="SYNTHETIC", sleep=lambda s: None) == 0
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
        assert c["result"] in ("PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE_MARKET_CLOSED", "NOT_CONNECTED")
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
    assert _crit(doc, "C5")["result"] == "FAIL"  # commission single-source, contract not verified
    assert _crit(doc, "C6")["result"] == "PASS"  # synthetic bars are built from bid
    c7 = _crit(doc, "C7")
    assert c7["result"] == "NOT_CONNECTED" and c7["metrics"]["NEWS_CALENDAR"] == "NOT_CONNECTED"
    assert UNAPPROVED_TZ_LABEL in md  # A8: UTC-derived tables labelled


def test_c4_ranks_true_rule_first(unconfirmed):
    _, doc, _ = unconfirmed
    rows = _crit(doc, "C4")["tables"][0]["rows"]
    # Without an official NFP calendar the base offset k is not identifiable from anchors alone:
    # the whole US_DST family ties (approx NFP hits are shown but never used for ranking — D-NFP).
    top = rows[:4]
    assert {r["rule"] for r in top} == {"US_DST+0", "US_DST+1", "US_DST+2", "US_DST+3"}
    assert all(r["unexplained [America/New_York]"] == 1 for r in top)  # Good Friday week
    assert all(r["unexplained [America/New_York]"] > 1 for r in rows[4:])
    rows = sorted(rows, key=lambda r: r["rule"] != "US_DST+2")
    # both frames side by side (D-C4); in UTC the NY-anchored session looks shifted
    assert rows[0]["unexplained [UTC]"] > 1
    assert rows[0]["nfp_hits_official"] == "UNKNOWN"  # no BLS calendar file
    c4 = _crit(doc, "C4")
    assert c4["metrics"]["nfp_approx_not_evidence"]["label"] == "approx — not evidence"


def test_c5_bar_spread_mapping(unconfirmed):
    _, doc, _ = unconfirmed
    m = _crit(doc, "C5")["metrics"]
    assert m["bar_spread_mapping"]["best_matching_statistic"] == "open"
    assert m["spread_ticks"]["status"] == "SINGLE_SOURCE"
    assert m["slippage"]["status"] == "MISSING"
    assert m["commission"]["status"] == "SINGLE_SOURCE"  # deals only, no official value


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


OFFICIAL = """
[official_costs.commission]
commission_per_lot_round_turn = {v}
source_url = "https://example.invalid/ftmo-commissions"
verified_date = "2026-10-14"
"""


def _write_official(cfg_path, value, with_source=True):
    text = OFFICIAL.format(v=value)
    if not with_source:
        text = "\n[official_costs.commission]\ncommission_per_lot_round_turn = %s\n" % value
    cfg_path.write_text(cfg_path.read_text() + text)


@pytest.mark.parametrize("value,with_source,expected", [
    (5.0, True, "VERIFIED"),         # |-5.0| vs 5.0
    (5.005, True, "VERIFIED"),       # within 0.01 tolerance
    (6.0, True, "CONFLICT"),
    (5.0, False, "SINGLE_SOURCE"),   # official without URL/date is ignored
])
def test_commission_verification(tmp_path, value, with_source, expected):
    from aurvex_lens.common.config import load_config
    from tests.conftest import write_config
    p = write_config(tmp_path)
    _write_official(p, value, with_source)
    _, doc, _ = _report(load_config(p))
    com = _crit(doc, "C5")["metrics"]["commission"]
    assert com["status"] == expected
    agg = com["deal_aggregates"]
    assert agg["round_turn_per_lot"] == {"n": 3, "median": -5.0, "min": -5.0, "max": -5.0}
    assert agg["per_side_per_lot"]["IN"]["n"] == 4 and agg["per_side_per_lot"]["OUT"]["n"] == 4
    assert agg["per_side_per_lot"]["OUT"]["median"] == -2.5


@pytest.mark.parametrize("mode,reason", [("none", "NO_DEALS"), ("denied", "ACCESS_DENIED")])
def test_commission_missing_reasons(make_cfg, mode, reason):
    _, doc, _ = _report(make_cfg(), deals_mode=mode)
    com = _crit(doc, "C5")["metrics"]["commission"]
    assert com["status"] == "MISSING" and com["reason"] == reason
    assert com["deal_aggregates"]["reason"] == reason


def test_no_individual_deal_data_anywhere(make_cfg, capsys):
    from tests.fixtures.synthetic import fake_mt5 as F
    cfg = make_cfg()
    _report(cfg)
    texts = [capsys.readouterr().out]
    for f in cfg.data_dir.rglob("*"):
        if f.is_file():
            texts.append(f.read_bytes().decode("utf-8", errors="ignore"))
    blob = "\n".join(texts)
    forbidden = [str(F.DEAL_PRICE), str(F.DEAL_PROFIT), str(F.DEAL_TICKET_BASE + 1), str(F.DEAL_POSITION_BASE),
                 str(F.DEAL_POSITION_BASE + 1), str(F.DEAL_TIME)[:7], "position_id\":", "\"ticket\":"]
    for token in forbidden:
        assert token not in blob, token
    # but the aggregates are there
    assert "round_turn_per_lot" in blob


def test_gate_not_connected_is_not_pass(unconfirmed):
    from aurvex_lens.quality.result import CriterionResult, data_gate, is_pass
    _, doc, md = unconfirmed
    gate = doc["header"]["phase1_data_gate"]
    assert gate["status"] == "DATA_INSUFFICIENT"
    assert {"id": "C7", "result": "NOT_CONNECTED"} in gate["not_passing"]
    assert not is_pass("NOT_CONNECTED")
    only_c7 = [CriterionResult("C1", "x", "PASS", "m"), CriterionResult("C7", "x", "NOT_CONNECTED", "m")]
    assert data_gate(only_c7)["status"] == "DATA_INSUFFICIENT"
    assert data_gate([CriterionResult("C1", "x", "PASS", "m")])["status"] == "DATA_SUFFICIENT"
    assert "phase1_data_gate: **DATA_INSUFFICIENT**" in md


def test_nfp_official_calendar_used(tmp_path):
    from aurvex_lens.common.config import load_config
    from tests.conftest import write_config
    cal = tmp_path / "bls.csv"
    cal.write_text("date,release_time_et\n2026-03-06,08:30\n")
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[analysis]", f"[analysis]\nnfp_calendar_path = '{cal.as_posix()}'"))
    _, doc, _ = _report(load_config(p))
    c4 = _crit(doc, "C4")
    assert c4["metrics"]["nfp_official"]["calendar_status"] == "LOADED"
    rows = {r["rule"]: r for r in c4["tables"][0]["rows"]}
    assert rows["US_DST+2"]["nfp_hits_official"] == 1 and rows["US_DST+1"]["nfp_hits_official"] == 0
    assert c4["tables"][0]["rows"][0]["rule"] == "US_DST+2"  # official evidence breaks the tie
