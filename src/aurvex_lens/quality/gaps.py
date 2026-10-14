"""C2 — missing data, separated from market closures.

Gap = consecutive bars further apart than one timeframe. Each missing bar
slot [t, t+tf) is tested against weekly closure intervals (server time):
- confirmed closures come from the user (config [confirmations].closures),
- candidate closures are recurring gap patterns detected in the data.
Classes: EXPECTED_CLOSURE, CLOSURE_CANDIDATE, HOLIDAY_CANDIDATE, UNEXPLAINED.
Only UNEXPLAINED counts as a data outage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

WEEK_MIN = 7 * 1440
DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# 1970-01-01 was a Thursday -> epoch minute 0 is week-minute 3*1440.
_EPOCH_WEEK_OFFSET = 3 * 1440

EXPECTED_CLOSURE = "EXPECTED_CLOSURE"
CLOSURE_CANDIDATE = "CLOSURE_CANDIDATE"
HOLIDAY_CANDIDATE = "HOLIDAY_CANDIDATE"
UNEXPLAINED = "UNEXPLAINED"


@dataclass(frozen=True)
class WeeklyInterval:
    start: int  # week-minute, Monday 00:00 server = 0
    end: int

    @property
    def length(self) -> int:
        return (self.end - self.start) % WEEK_MIN

    def label(self) -> str:
        return f"{fmt_wm(self.start)} -> {fmt_wm(self.end)}"


def week_minute(epoch_sec: np.ndarray | int) -> np.ndarray:
    return (np.asarray(epoch_sec) // 60 + _EPOCH_WEEK_OFFSET) % WEEK_MIN


def fmt_wm(wm: int) -> str:
    d, r = divmod(int(wm), 1440)
    return f"{DOW[d]} {r // 60:02d}:{r % 60:02d}"


def parse_interval(s: str) -> WeeklyInterval:
    a, b = (p.strip() for p in s.split("->"))

    def p(x: str) -> int:
        day, hm = x.split()
        h, m = hm.split(":")
        return DOW.index(day[:3].title()) * 1440 + int(h) * 60 + int(m)

    return WeeklyInterval(p(a), p(b))


def find_gaps(times: np.ndarray, tf_sec: int) -> pd.DataFrame:
    t = np.asarray(times, dtype="int64")
    if len(t) < 2:
        return pd.DataFrame(columns=["gap_start", "gap_end", "missing_bars"])
    d = np.diff(t)
    idx = np.nonzero(d > tf_sec)[0]
    starts = t[idx] + tf_sec
    ends = t[idx + 1]
    missing = (ends - starts + tf_sec - 1) // tf_sec
    return pd.DataFrame({"gap_start": starts, "gap_end": ends, "missing_bars": missing})


def detect_candidates(gaps: pd.DataFrame, min_recurrence: int) -> list[tuple[WeeklyInterval, int]]:
    """Recurring (start week-minute, end week-minute) patterns."""
    if gaps.empty:
        return []
    keys = pd.DataFrame({"s": week_minute(gaps["gap_start"].to_numpy()),
                         "e": week_minute(gaps["gap_end"].to_numpy()),
                         "len": (gaps["gap_end"] - gaps["gap_start"]).to_numpy() // 60})
    keys = keys[keys["len"] < WEEK_MIN]
    counts = keys.groupby(["s", "e"]).size()
    out = [(WeeklyInterval(int(s), int(e)), int(n)) for (s, e), n in counts.items() if n >= min_recurrence]
    return sorted(out, key=lambda x: x[0].start)


def _slot_inside(wm: np.ndarray, tf_min: int, intervals: list[WeeklyInterval]) -> np.ndarray:
    inside = np.zeros(len(wm), dtype=bool)
    for iv in intervals:
        inside |= ((wm - iv.start) % WEEK_MIN + tf_min) <= iv.length
    return inside


def classify_gaps(gaps: pd.DataFrame, tf_sec: int, confirmed: list[WeeklyInterval],
                  candidates: list[WeeklyInterval], confirmed_holidays: set[str]) -> pd.DataFrame:
    """Return gaps with columns: cls, closure_slots, other_slots, other_dates."""
    g = gaps.copy().reset_index(drop=True)
    if g.empty:
        for c in ("cls", "closure_slots", "other_slots", "other_dates", "minutes"):
            g[c] = pd.Series(dtype="object")
        return g
    tf_min = tf_sec // 60
    n = g["missing_bars"].to_numpy().astype("int64")
    gap_id = np.repeat(np.arange(len(g)), n)
    offs = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    slot_t = np.repeat(g["gap_start"].to_numpy(), n) + offs * tf_sec
    wm = week_minute(slot_t)
    in_conf = _slot_inside(wm, tf_min, confirmed)
    in_cand = _slot_inside(wm, tf_min, candidates)
    in_any = in_conf | in_cand
    day = slot_t // 86400

    conf_cnt = np.bincount(gap_id, weights=in_conf, minlength=len(g)).astype(int)
    any_cnt = np.bincount(gap_id, weights=in_any, minlength=len(g)).astype(int)
    classes, other_dates_col = [], []
    other_mask = ~in_any
    other_days = pd.Series(day[other_mask]).groupby(gap_id[other_mask]).unique()
    for i in range(len(g)):
        total = int(n[i])
        dates = sorted(datetime.fromtimestamp(int(d) * 86400, tz=UTC).strftime("%Y-%m-%d")
                       for d in other_days.get(i, []))
        other_dates_col.append(dates)
        if conf_cnt[i] == total:
            classes.append(EXPECTED_CLOSURE)
        elif any_cnt[i] == total:
            classes.append(CLOSURE_CANDIDATE)
        elif dates and set(dates) <= confirmed_holidays and any_cnt[i] > 0:
            classes.append(EXPECTED_CLOSURE)
        elif any_cnt[i] > 0:
            classes.append(HOLIDAY_CANDIDATE)
        else:
            classes.append(UNEXPLAINED)
    g["cls"] = classes
    g["closure_slots"] = any_cnt
    g["other_slots"] = n - any_cnt
    g["other_dates"] = other_dates_col
    g["minutes"] = n * tf_min
    return g


def gap_summary(classified: pd.DataFrame, rows: int, tf_min: int) -> dict:
    if classified.empty:
        return {"gaps_total": 0, "by_class": {}, "unexplained_missing_bars": 0,
                "expected_bars": rows, "unexplained_ratio": 0.0, "max_unexplained_gap_minutes": 0,
                "unexplained_duration_buckets": {}}
    by = classified.groupby("cls")["missing_bars"].agg(["count", "sum"])
    unexp = classified[classified["cls"] == UNEXPLAINED]
    holiday = classified[classified["cls"] == HOLIDAY_CANDIDATE]
    unexp_bars = int(unexp["missing_bars"].sum())
    non_closure_missing = unexp_bars + int(holiday["other_slots"].sum())
    expected = rows + non_closure_missing
    buckets = {}
    if not unexp.empty:
        mins = unexp["minutes"]
        buckets = {
            f"<= {2 * tf_min} min": int((mins <= 2 * tf_min).sum()),
            f"{2 * tf_min}-30 min": int(((mins > 2 * tf_min) & (mins <= 30)).sum()),
            "30-240 min": int(((mins > 30) & (mins <= 240)).sum()),
            "> 240 min": int((mins > 240).sum()),
        }
    return {
        "gaps_total": int(len(classified)),
        "by_class": {k: {"gaps": int(v["count"]), "missing_bars": int(v["sum"])} for k, v in by.iterrows()},
        "unexplained_missing_bars": unexp_bars,
        "expected_bars": int(expected),
        "unexplained_ratio": (unexp_bars / (rows + unexp_bars)) if (rows + unexp_bars) else 0.0,
        "max_unexplained_gap_minutes": int(unexp["minutes"].max()) if not unexp.empty else 0,
        "unexplained_duration_buckets": buckets,
    }


def resample_m1(m1: pd.DataFrame, tf_sec: int) -> pd.DataFrame:
    b = m1["time_server"] - m1["time_server"] % tf_sec
    g = m1.groupby(b)
    out = pd.DataFrame({
        "open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close": g["close"].last(), "tick_volume": g["tick_volume"].sum(),
    })
    out.index.name = "time_server"
    return out.reset_index()


def cross_tf_consistency(m1: pd.DataFrame, other: pd.DataFrame, tf_sec: int, point: float | None) -> dict:
    if m1.empty or other.empty:
        return {"status": "UNKNOWN", "reason": "missing M1 or target timeframe data"}
    lo = int(m1["time_server"].iloc[0])
    lo = lo - lo % tf_sec + tf_sec  # first fully covered bin
    hi = int(m1["time_server"].iloc[-1])
    hi = hi - hi % tf_sec  # last bin may be incomplete -> exclude
    rs = resample_m1(m1, tf_sec)
    rs = rs[(rs["time_server"] >= lo) & (rs["time_server"] < hi)]
    ot = other[(other["time_server"] >= lo) & (other["time_server"] < hi)]
    merged = rs.merge(ot, on="time_server", how="outer", suffixes=("_m1", "_tf"), indicator=True)
    both = merged[merged["_merge"] == "both"]
    tol = (point / 2) if point else 1e-9
    mism = {}
    for c in ("open", "high", "low", "close"):
        mism[c] = int((np.abs(both[f"{c}_m1"] - both[f"{c}_tf"]) > tol).sum())
    mism["tick_volume"] = int((both["tick_volume_m1"] != both["tick_volume_tf"]).sum())
    any_price = np.zeros(len(both), dtype=bool)
    for c in ("open", "high", "low", "close"):
        any_price |= (np.abs(both[f"{c}_m1"] - both[f"{c}_tf"]) > tol).to_numpy()
    return {
        "status": "MEASURED",
        "compared_range_server": [lo, hi],
        "bars_compared": int(len(both)),
        "only_in_resampled_m1": int((merged["_merge"] == "left_only").sum()),
        "only_in_terminal_tf": int((merged["_merge"] == "right_only").sum()),
        "mismatch_by_field": mism,
        "bars_with_any_price_mismatch": int(any_price.sum()),
        "price_mismatch_ratio": float(any_price.mean()) if len(both) else 0.0,
        "price_tolerance": tol,
    }
