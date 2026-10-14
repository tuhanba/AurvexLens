"""C4 — clock accuracy and historical server-time (DST) rule mapping.

The current server offset is NOT applied to all history. Candidate rules
(FIXED+k, EU_DST+k, US_DST+k) are tested week by week: under the correct
rule, recurring session anchors (weekly open/close, daily break) map to a
constant time in the reference frame. Weeks where US and EU DST disagree are
the discriminating weeks and are reported separately. A second check maps the
volatility spike on candidate US payroll Fridays to New York time.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from aurvex_lens.quality.gaps import (
    CLOSURE_CANDIDATE, EXPECTED_CLOSURE, WEEK_MIN, fmt_wm,
)
from aurvex_lens.quality.result import (
    FAIL, PASS, UNAPPROVED_TZ_LABEL, UNKNOWN, CriterionResult, combine,
)

_STD = {"Europe/London": 0, "America/New_York": -5 * 3600}
_RULE_TZ = {"EU_DST": "Europe/London", "US_DST": "America/New_York"}


def _tz_offset_s(tz: str, utc: np.ndarray) -> np.ndarray:
    if tz == "UTC":
        return np.zeros(len(utc), dtype="int64")
    ts = pd.to_datetime(np.asarray(utc, dtype="int64"), unit="s", utc=True)
    local = ts.tz_convert(tz).tz_localize(None)
    return ((local - ts.tz_localize(None)).total_seconds()).to_numpy().astype("int64")


def _dst(tz: str, utc: np.ndarray) -> np.ndarray:
    return (_tz_offset_s(tz, utc) - _STD[tz]) // 3600


def parse_rule(rule: str) -> tuple[str, int]:
    kind, k = rule.split("+")
    if kind not in ("FIXED", "EU_DST", "US_DST"):
        raise ValueError(f"unknown rule {rule}")
    return kind, int(k)


def rule_offset_s(rule: str, utc: np.ndarray) -> np.ndarray:
    """Server-minus-UTC offset in seconds at the given UTC instants."""
    kind, k = parse_rule(rule)
    base = np.full(len(np.asarray(utc)), k * 3600, dtype="int64")
    if kind == "FIXED":
        return base
    return base + _dst(_RULE_TZ[kind], np.asarray(utc)) * 3600


def server_to_utc(rule: str, server: np.ndarray) -> np.ndarray:
    server = np.asarray(server, dtype="int64")
    _, k = parse_rule(rule)
    utc = server - k * 3600
    for _ in range(2):
        utc = server - rule_offset_s(rule, utc)
    return utc


def candidate_rules(base_offsets: tuple[int, ...]) -> list[str]:
    return [f"{kind}+{k}" for k in base_offsets for kind in ("FIXED", "EU_DST", "US_DST")]


def _week_id(server: np.ndarray) -> np.ndarray:
    """Saturday-anchored weeks so one trading week's open and close share an id."""
    return (np.asarray(server, dtype="int64") // 60 - 2 * 1440) // WEEK_MIN


def week_start_date(wid: int) -> str:
    return datetime.fromtimestamp(int((wid * WEEK_MIN + 2 * 1440) * 60), tz=UTC).strftime("%Y-%m-%d")


def extract_events(classified_gaps: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g in classified_gaps.itertuples():
        dur = g.gap_end - g.gap_start
        if dur >= 86400:
            rows.append(("weekly_close", g.gap_start))
            rows.append(("weekly_open", g.gap_end))
        elif g.cls in (EXPECTED_CLOSURE, CLOSURE_CANDIDATE):
            rows.append(("break_start", g.gap_start))
            rows.append(("break_end", g.gap_end))
    ev = pd.DataFrame(rows, columns=["event", "server"])
    if not ev.empty:
        ev["week"] = _week_id(ev["server"].to_numpy())
    return ev


def _frame_key(event: str, local: np.ndarray) -> np.ndarray:
    m = np.asarray(local, dtype="int64") // 60
    if event.startswith("weekly"):
        return (m + 3 * 1440) % WEEK_MIN  # week-minute, Monday-based
    return m % 1440


def rule_match_table(events: pd.DataFrame, rules: list[str], frame: str) -> pd.DataFrame:
    """weeks x rules boolean match (True = all anchors in that week at modal frame time)."""
    if events.empty:
        return pd.DataFrame()
    out = {}
    for rule in rules:
        utc = server_to_utc(rule, events["server"].to_numpy())
        local = utc + _tz_offset_s(frame, utc)
        keys = np.empty(len(events), dtype="int64")
        for ev in events["event"].unique():
            mask = (events["event"] == ev).to_numpy()
            keys[mask] = _frame_key(ev, local[mask])
        e = events.assign(key=keys)
        modes = e.groupby("event")["key"].agg(lambda s: s.value_counts().idxmax())
        e["ok"] = e["key"].to_numpy() == e["event"].map(modes).to_numpy()
        out[rule] = e.groupby("week")["ok"].all()
    return pd.DataFrame(out)


def modal_times(events: pd.DataFrame, rule: str, frame: str) -> dict[str, str]:
    if events.empty:
        return {}
    utc = server_to_utc(rule, events["server"].to_numpy())
    local = utc + _tz_offset_s(frame, utc)
    res = {}
    for ev in events["event"].unique():
        mask = (events["event"] == ev).to_numpy()
        k = pd.Series(_frame_key(ev, local[mask])).value_counts().idxmax()
        res[ev] = fmt_wm(k) if ev.startswith("weekly") else f"{k // 60:02d}:{k % 60:02d}"
    return res


def divergence_weeks(weeks: np.ndarray) -> np.ndarray:
    """True for weeks where US and EU DST states differ (mid-week sample)."""
    mid = ((np.asarray(weeks, dtype="int64") * WEEK_MIN + 2 * 1440) * 60) + int(4.5 * 86400)
    return _dst("America/New_York", mid) != _dst("Europe/London", mid)


def first_fridays(first_server: int, last_server: int) -> list[date]:
    d0 = datetime.fromtimestamp(first_server, tz=UTC).date().replace(day=1)
    end = datetime.fromtimestamp(last_server, tz=UTC).date()
    out = []
    while d0 <= end:
        fri = d0 + timedelta(days=(4 - d0.weekday()) % 7)
        out.append(fri)
        d0 = (d0.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def nfp_check(bars: pd.DataFrame, tf_min: int, rules: list[str]) -> dict[str, Any]:
    if bars is None or bars.empty:
        return {"status": UNKNOWN, "reason": "no bars"}
    t = bars["time_server"].to_numpy()
    day = t // 86400
    rng = (bars["high"] - bars["low"]).to_numpy()
    spikes = []
    for fri in first_fridays(int(t[0]), int(t[-1])):
        dnum = (datetime(fri.year, fri.month, fri.day, tzinfo=UTC).timestamp()) // 86400
        idx = np.nonzero(day == dnum)[0]
        if len(idx) < 10:
            continue
        spikes.append((fri.isoformat(), int(t[idx[np.argmax(rng[idx])]])))
    expected = 8 * 60 + 30 - (8 * 60 + 30) % tf_min
    res = {"candidates": len(spikes), "expected_ny_bar_start": f"{expected // 60:02d}:{expected % 60:02d}",
           "per_rule_hits": {}, "note": ("Candidate dates = first Friday of month (approximation, not the official "
                                         "BLS schedule). Spike = bar with max high-low on that server date.")}
    if not spikes:
        return res
    st = np.array([s for _, s in spikes])
    for rule in rules:
        utc = server_to_utc(rule, st)
        ny = utc + _tz_offset_s("America/New_York", utc)
        res["per_rule_hits"][rule] = int((((ny // 60) % 1440) == expected).sum())
    return res


def live_offset(live: dict | None) -> dict[str, Any]:
    if not live or not live.get("samples"):
        return {"status": UNKNOWN}
    diffs = [x["tick_time_msc_server"] / 1000 - x["system_utc_ms"] / 1000 for x in live["samples"]
             if x["tick_time_msc_server"] is not None]
    if not diffs:
        return {"status": UNKNOWN}
    med = float(np.median(diffs))
    rounded = round(med / 900) * 900
    return {"status": "MEASURED", "median_raw_diff_s": med, "rounded_offset_s": int(rounded),
            "rounded_offset_h": rounded / 3600, "residual_s": med - rounded,
            "system_utc_ms": live["samples"][-1]["system_utc_ms"],
            "note": "server tick time − system UTC; residual includes tick staleness (large if market closed)"}


def evaluate_c4(event_tf: str | None, event_gaps: pd.DataFrame | None, event_bars: pd.DataFrame | None,
                live: dict | None, clock: dict | None, base_offsets: tuple[int, ...], frame: str,
                approved_rule: str | None, confirmed_holidays: set[str], thresholds: dict,
                evidence: list[str]) -> tuple[CriterionResult, pd.DataFrame]:
    rules = candidate_rules(base_offsets)
    lo = live_offset(live)
    clock_status = (clock or {}).get("status", UNKNOWN)
    metrics: dict[str, Any] = {"local_clock": {"status": clock_status, "reason": (clock or {}).get("reason")},
                               "current_server_offset": lo, "event_timeframe": event_tf,
                               "reference_frame": frame, "candidate_rules": rules, "approved_rule": approved_rule}
    method = ("Anchors (weekly open/close, daily break) from classified gaps; each candidate rule converts server→UTC, "
              f"then to reference frame '{frame}'; a week matches if all anchors equal the modal frame time. "
              "US/EU DST divergence weeks reported separately. NFP spike check in America/New_York.")
    if event_gaps is None or event_bars is None or event_bars.empty:
        return CriterionResult("C4", "Saat doğruluğu", UNKNOWN, method, metrics, evidence=evidence,
                               notes=["no bars for event extraction"]), pd.DataFrame()
    events = extract_events(event_gaps)
    table = rule_match_table(events, rules, frame)
    rows = []
    if not table.empty:
        div = divergence_weeks(table.index.to_numpy())
        for rule in rules:
            col = table[rule]
            row = {"rule": rule, "weeks": int(len(col)), "matched": int(col.sum()),
                   "unexplained": int((~col).sum()),
                   "divergence_weeks": int(div.sum()), "divergence_matched": int(col[div].sum())}
            if lo.get("status") == "MEASURED":
                off = int(rule_offset_s(rule, np.array([lo["system_utc_ms"] // 1000]))[0])
                row["consistent_with_live_offset"] = off == lo["rounded_offset_s"]
            else:
                row["consistent_with_live_offset"] = None
            row["modal_anchor_times"] = modal_times(events, rule, frame)
            rows.append(row)
    nfp = nfp_check(event_bars, int(event_tf[1:]) if event_tf.startswith("M") else 60, rules)
    for r in rows:
        r["nfp_hits"] = nfp.get("per_rule_hits", {}).get(r["rule"])
    ranked = sorted(rows, key=lambda r: (r["unexplained"], -(r["nfp_hits"] or 0),
                                         r["consistent_with_live_offset"] is not True))
    metrics["nfp_check"] = nfp
    unexplained_all = []
    if not table.empty:
        none_ok = ~table.any(axis=1)
        unexplained_all = [week_start_date(w) for w in table.index[none_ok]]
    metrics["weeks_unexplained_under_all_rules"] = unexplained_all
    tables = [{"title": "Aday kural özeti (rule_match)", "utc": True,
               "columns": ["rule", "weeks", "matched", "unexplained", "divergence_weeks", "divergence_matched",
                           "nfp_hits", "consistent_with_live_offset", "modal_anchor_times"],
               "rows": ranked}]
    notes = [UNAPPROVED_TZ_LABEL] if not approved_rule else []
    sub = []
    max_unexp = thresholds.get("c4", {}).get("max_unexplained_weeks")
    clock_res = PASS if clock_status == "SYNCED" else (FAIL if clock_status == "NOT_SYNCED" else UNKNOWN)
    sub.append({"check": "local_clock_synced", "result": clock_res})
    if not approved_rule:
        sub.append({"check": "approved_rule", "result": UNKNOWN, "reason": "O3 not approved by user"})
        result = UNKNOWN
    else:
        if approved_rule not in table.columns:
            sub.append({"check": "approved_rule", "result": UNKNOWN,
                        "reason": f"approved rule {approved_rule} not among evaluated candidates"})
        else:
            bad = table.index[~table[approved_rule]]
            bad_dates = []
            for w in bad:
                start = datetime.fromisoformat(week_start_date(w))
                days = {(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
                if not days & confirmed_holidays:
                    bad_dates.append(week_start_date(w))
            r = UNKNOWN if max_unexp is None else (PASS if len(bad_dates) <= max_unexp else FAIL)
            sub.append({"check": "approved_rule_unexplained_weeks", "result": r, "value": len(bad_dates),
                        "weeks": bad_dates, "threshold": max_unexp})
        result = combine([s["result"] for s in sub])
    return CriterionResult("C4", "Saat doğruluğu", result, method, metrics, sub_results=sub,
                           evidence=evidence, notes=notes, tables=tables), table
