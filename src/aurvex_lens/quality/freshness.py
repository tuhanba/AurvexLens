"""C3 — price freshness (from live probe recorded at extraction time)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aurvex_lens.quality.gaps import WeeklyInterval, week_minute
from aurvex_lens.quality.result import (
    FAIL, NOT_APPLICABLE_MARKET_CLOSED, PASS, UNKNOWN, CriterionResult,
)


def tick_interval_stats(ticks: pd.DataFrame | None) -> dict[str, Any]:
    if ticks is None or len(ticks) < 2:
        return {"status": UNKNOWN, "reason": "no recent ticks"}
    d = np.diff(ticks["time_msc_server"].to_numpy()) / 1000.0
    d = d[(d >= 0) & (d < 300)]  # exclude closures/breaks (>5 min) from 'normal' frequency
    if len(d) == 0:
        return {"status": UNKNOWN, "reason": "no intervals under 300 s"}
    return {"intervals_considered": int(len(d)), "median_s": float(np.median(d)),
            "p95_s": float(np.percentile(d, 95)), "p99_s": float(np.percentile(d, 99)),
            "note": "inter-tick intervals < 300 s from recent full ticks"}


def evaluate_c3(live: dict | None, approved_offset_fn, confirmed_closures: list[WeeklyInterval],
                thresholds: dict, recent_ticks: pd.DataFrame | None, evidence: list[str]) -> CriterionResult:
    """approved_offset_fn: callable(utc_epoch_array)->offset_seconds, or None if O3 not approved."""
    max_age = thresholds.get("c3", {}).get("max_tick_age_seconds")
    method = ("symbol_info_tick time_msc (server) vs local system UTC; requires approved server-time rule. "
              "Market state from confirmed closures. terminal_info().connected checked on each sample.")
    metrics: dict[str, Any] = {"normal_tick_frequency": tick_interval_stats(recent_ticks),
                               "threshold_max_tick_age_s": max_age}
    notes = []
    if not live or not live.get("samples"):
        return CriterionResult("C3", "Fiyat güncelliği", UNKNOWN, method, metrics, evidence=evidence,
                               notes=["live probe missing"])
    s = live["samples"]
    connected = [x["terminal_connected"] for x in s]
    metrics["terminal_connected_samples"] = connected
    raw = [(x["tick_time_msc_server"] / 1000 - x["system_utc_ms"] / 1000) for x in s
           if x["tick_time_msc_server"] is not None]
    metrics["raw_server_minus_system_utc_s"] = {"median": float(np.median(raw)) if raw else None,
                                                "note": "includes unknown server UTC offset; not an age"}
    if any(c is False for c in connected):
        return CriterionResult("C3", "Fiyat güncelliği", FAIL, method, metrics, evidence=evidence,
                               notes=["terminal_info().connected was False in at least one sample"])
    if any(c is None for c in connected) or not raw:
        return CriterionResult("C3", "Fiyat güncelliği", UNKNOWN, method, metrics, evidence=evidence,
                               notes=["connected flag or tick missing in samples"])
    if approved_offset_fn is None:
        notes.append("Server-time rule (O3) not approved → tick age cannot be computed.")
        return CriterionResult("C3", "Fiyat güncelliği", UNKNOWN, method, metrics, evidence=evidence, notes=notes)
    if not confirmed_closures:
        notes.append("No confirmed closures → market open/closed state unknown.")
        return CriterionResult("C3", "Fiyat güncelliği", UNKNOWN, method, metrics, evidence=evidence, notes=notes)
    ages = []
    closed = []
    for x in s:
        if x["tick_time_msc_server"] is None:
            continue
        sys_utc = x["system_utc_ms"] / 1000
        now_server = sys_utc + float(approved_offset_fn(np.array([int(sys_utc)]))[0])
        wm = int(week_minute(np.array([int(now_server)]))[0])
        closed.append(any(((wm - iv.start) % (7 * 1440)) < iv.length for iv in confirmed_closures))
        tick_server = x["tick_time_msc_server"] / 1000
        offset = float(approved_offset_fn(np.array([int(tick_server)]))[0])
        ages.append(sys_utc - (tick_server - offset))
    metrics["tick_age_s"] = {"max": max(ages), "median": float(np.median(ages))}
    if all(closed):
        return CriterionResult("C3", "Fiyat güncelliği", NOT_APPLICABLE_MARKET_CLOSED, method, metrics,
                               evidence=evidence, notes=["market closed at probe time (confirmed closures)"])
    if max_age is None:
        return CriterionResult("C3", "Fiyat güncelliği", UNKNOWN, method, metrics, evidence=evidence,
                               notes=["no threshold"])
    return CriterionResult("C3", "Fiyat güncelliği", PASS if max(ages) <= max_age else FAIL, method, metrics,
                           evidence=evidence, notes=notes)
