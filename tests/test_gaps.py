"""C2 gap classification on SYNTHETIC — NOT MARKET DATA."""

from __future__ import annotations

import numpy as np

from aurvex_lens.quality import gaps as G
from tests.fixtures.synthetic import synth


def _classify(tf_min, confirmed=(), holidays=()):
    m1 = synth.bars(1)
    raw_m1 = G.find_gaps(m1["time"].to_numpy(), 60)
    cand = [iv for iv, _ in G.detect_candidates(raw_m1, 4)]
    df = synth.bars(tf_min)
    raw = G.find_gaps(df["time"].to_numpy(), tf_min * 60)
    conf = [G.parse_interval(s) for s in confirmed]
    return G.classify_gaps(raw, tf_min * 60, conf, [c for c in cand if c not in conf], set(holidays)), cand


def test_interval_roundtrip_and_wrap():
    iv = G.parse_interval("Sat 00:00 -> Mon 01:00")
    assert iv.label() == "Sat 00:00 -> Mon 01:00"
    assert iv.length == 2 * 1440 + 60
    assert G.parse_interval("Sun 22:00 -> Mon 01:00").length == 180  # wraps week boundary
    assert G.fmt_wm(int(G.week_minute(np.array([synth.START]))[0])) == "Mon 00:00"


def test_candidates_detected():
    _, cand = _classify(1)
    labels = {c.label() for c in cand}
    assert "Sat 00:00 -> Mon 01:00" in labels
    assert {"Tue 00:00 -> Tue 01:00", "Wed 00:00 -> Wed 01:00", "Thu 00:00 -> Thu 01:00"} <= labels


def test_classes_unconfirmed():
    c, _ = _classify(1)
    unexp = c[c.cls == G.UNEXPLAINED]
    assert len(unexp) == 1
    assert unexp.iloc[0].gap_start == synth.GAP_START and unexp.iloc[0].minutes == 45
    hol = c[c.cls == G.HOLIDAY_CANDIDATE]
    assert len(hol) == 1 and hol.iloc[0].other_dates == ["2026-04-03"]
    assert (c.cls == G.EXPECTED_CLOSURE).sum() == 0
    assert (c.cls == G.CLOSURE_CANDIDATE).sum() > 0


def test_classes_confirmed_all_tfs():
    confirmed = ["Sat 00:00 -> Mon 01:00"] + [f"{d} 00:00 -> {d} 01:00" for d in ("Tue", "Wed", "Thu", "Fri")]
    for tf in (1, 5, 15, 60):
        c, _ = _classify(tf, confirmed, holidays=["2026-04-03"])
        assert set(c.cls) <= {G.EXPECTED_CLOSURE, G.UNEXPLAINED}, (tf, set(c.cls))
        unexp = c[c.cls == G.UNEXPLAINED]
        # 10:00-10:45 gap is invisible at H1 (the 10:00 bar still has 10:45-10:59 data)
        assert len(unexp) == (0 if tf == 60 else 1)


def test_summary_ratio():
    c, _ = _classify(1)
    s = G.gap_summary(c, len(synth.m1()), 1)
    assert s["unexplained_missing_bars"] == 45
    assert s["max_unexplained_gap_minutes"] == 45
    assert abs(s["unexplained_ratio"] - 45 / (len(synth.m1()) + 45)) < 1e-12


def test_cross_tf_consistency_exact():
    m1 = synth.m1().rename(columns={"time": "time_server"})
    for tf in (5, 15, 60):
        other = synth.bars(tf).rename(columns={"time": "time_server"})
        r = G.cross_tf_consistency(m1, other, tf * 60, synth.POINT)
        assert r["bars_compared"] > 0 and r["bars_with_any_price_mismatch"] == 0


def test_cross_tf_detects_mismatch():
    m1 = synth.m1().rename(columns={"time": "time_server"})
    h1 = synth.bars(60).rename(columns={"time": "time_server"}).copy()
    h1.loc[100, "high"] += 0.5
    r = G.cross_tf_consistency(m1, h1, 3600, synth.POINT)
    assert r["bars_with_any_price_mismatch"] == 1
