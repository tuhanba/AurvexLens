"""C4 server-time rule mapping on SYNTHETIC — NOT MARKET DATA (true rule: US_DST+2)."""

from __future__ import annotations

import calendar

import numpy as np

from aurvex_lens.quality import gaps as G
from aurvex_lens.quality import server_time as S
from tests.fixtures.synthetic import synth


def test_rule_offsets_and_transitions():
    # US DST 2026 starts 2026-03-08 07:00 UTC, EU 2026-03-29 01:00 UTC
    before = calendar.timegm((2026, 3, 8, 6, 0, 0))
    after = calendar.timegm((2026, 3, 8, 8, 0, 0))
    o = S.rule_offset_s("US_DST+2", np.array([before, after]))
    assert list(o) == [7200, 10800]
    e = S.rule_offset_s("EU_DST+2", np.array([after, calendar.timegm((2026, 3, 29, 2, 0, 0))]))
    assert list(e) == [7200, 10800]
    assert list(S.rule_offset_s("FIXED+3", np.array([before, after]))) == [10800, 10800]


def test_server_to_utc_roundtrip():
    utc = np.array([calendar.timegm((2026, m, 15, 12, 0, 0)) for m in range(1, 13)])
    for rule in ("US_DST+2", "EU_DST+1", "FIXED+0"):
        server = utc + S.rule_offset_s(rule, utc)
        assert (S.server_to_utc(rule, server) == utc).all()


def test_divergence_weeks_march_2026():
    # Saturday-anchored week containing Wed 2026-03-18 is a divergence week; 2026-02-25 is not
    w = S._week_id(np.array([calendar.timegm((2026, 3, 18, 12, 0, 0)), calendar.timegm((2026, 2, 25, 12, 0, 0))]))
    assert list(S.divergence_weeks(w)) == [True, False]


def _events():
    m5 = synth.bars(5)
    raw = G.find_gaps(m5["time"].to_numpy(), 300)
    cand = [iv for iv, _ in G.detect_candidates(G.find_gaps(synth.m1()["time"].to_numpy(), 60), 4)]
    return S.extract_events(G.classify_gaps(raw, 300, [], cand, set()))


def test_true_rule_family_matches_in_ny_frame():
    ev = _events()
    rules = S.candidate_rules((0, 1, 2, 3))
    t = S.rule_match_table(ev, rules, "America/New_York")
    good_weeks = t["US_DST+2"]
    # Only the Good-Friday week deviates (holiday changes the weekly close anchor)
    assert (~good_weeks).sum() == 1
    for k in (0, 1, 2, 3):
        assert (~t[f"FIXED+{k}"]).sum() > 1  # fixed offsets break at the US DST switch
        assert (~t[f"EU_DST+{k}"]).sum() > 1  # EU rule breaks in divergence weeks


def test_utc_frame_prefers_fixed_offset():
    # Documents why the reference frame matters: NY-anchored sessions look shifted in UTC.
    t = S.rule_match_table(_events(), ["US_DST+2", "FIXED+2"], "UTC")
    assert (~t["FIXED+2"]).sum() < (~t["US_DST+2"]).sum()


def test_nfp_spike_identifies_offset():
    m5 = synth.bars(5).rename(columns={"time": "time_server"})
    r = S.nfp_check(m5, 5, ["US_DST+1", "US_DST+2", "US_DST+3", "FIXED+2"])
    assert r["candidates"] == 1
    # 2026-03-06 is before the US switch, so FIXED+2 == US_DST+2 on that date: the NFP check
    # pins the base offset, the weekly anchor table separates the DST families.
    assert r["per_rule_hits"] == {"US_DST+1": 0, "US_DST+2": 1, "US_DST+3": 0, "FIXED+2": 1}
