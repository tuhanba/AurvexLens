"""C5 — cost data sufficiency; C6 — bid/ask basis of bar OHLC (informational).

Source status per component: VERIFIED (two independent sources agree),
SINGLE_SOURCE, MISSING, CONFLICT (two sources disagree — never VERIFIED).
Bar `spread` is never assumed to be the real spread; it is labelled
"indicative" until its relation to tick spread is measured.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from aurvex_lens.quality.result import FAIL, PASS, UNKNOWN, CriterionResult

VERIFIED, SINGLE_SOURCE, MISSING, CONFLICT = "VERIFIED", "SINGLE_SOURCE", "MISSING", "CONFLICT"

CONTRACT_FIELDS = ("trade_contract_size", "trade_tick_size", "trade_tick_value", "volume_min",
                   "volume_step", "volume_max", "digits", "point")
SWAP_FIELDS = ("swap_mode", "swap_long", "swap_short", "swap_rollover3days")


def _valid_ticks(ticks: pd.DataFrame | None) -> pd.DataFrame:
    if ticks is None or ticks.empty:
        return pd.DataFrame()
    return ticks[(ticks["bid"] > 0) & (ticks["ask"] > 0)]


def spread_distribution(ticks: pd.DataFrame | None, point: float | None) -> dict[str, Any]:
    t = _valid_ticks(ticks)
    if t.empty or not point:
        return {"status": MISSING, "reason": "no valid recent ticks or point unknown"}
    sp = (t["ask"] - t["bid"]) / point
    hour = (t["time_server"] // 3600) % 24
    g = sp.groupby(hour)
    by_hour = pd.DataFrame({
        "ticks": g.size(), "min": g.min(), "p50": g.median(), "mean": g.mean(),
        "p90": g.quantile(0.9), "p99": g.quantile(0.99), "max": g.max(),
    }).round(2)
    by_hour.index.name = "server_hour"
    return {
        "status": SINGLE_SOURCE,
        "unit": "points", "ticks": int(len(t)),
        "window_server": [int(t["time_server"].iloc[0]), int(t["time_server"].iloc[-1])],
        "server_hours_covered": int(by_hour.shape[0]),
        "overall": {"min": float(sp.min()), "p50": float(sp.median()), "mean": float(sp.mean()),
                    "p90": float(sp.quantile(0.9)), "p99": float(sp.quantile(0.99)), "max": float(sp.max())},
        "by_server_hour": by_hour.reset_index().to_dict(orient="records"),
        "note": "Single feed (broker ticks). Grouped by server hour (not UTC).",
    }


def _tick_bins(ticks: pd.DataFrame, bar_sec: int) -> tuple[pd.DataFrame, int, int]:
    t = _valid_ticks(ticks)
    b = t["time_server"] - t["time_server"] % bar_sec
    lo = int(b.min()) + bar_sec  # drop possibly partial first/last bins
    hi = int(b.max()) - bar_sec
    return t.assign(bin=b), lo, hi


def bar_spread_mapping(ticks: pd.DataFrame | None, m1: pd.DataFrame | None, point: float | None) -> dict[str, Any]:
    if ticks is None or m1 is None or _valid_ticks(ticks).empty or m1.empty or not point:
        return {"status": UNKNOWN, "reason": "no overlap of M1 bars and recent ticks"}
    t, lo, hi = _tick_bins(ticks, 60)
    t = t.assign(sp=(t["ask"] - t["bid"]) / point)
    g = t.groupby("bin")["sp"]
    stats = pd.DataFrame({"min": g.min(), "mean": g.mean(), "open": g.first(), "close": g.last(), "max": g.max()})
    bars = m1[(m1["time_server"] >= lo) & (m1["time_server"] <= hi)].set_index("time_server")
    j = stats.join(bars["spread"], how="inner")
    if j.empty:
        return {"status": UNKNOWN, "reason": "no overlapping bins"}
    rates = {c: float((np.abs(j[c] - j["spread"]) <= 0.5).mean()) for c in ("min", "mean", "open", "close", "max")}
    best = max(rates, key=rates.get)
    return {"status": "MEASURED", "bars_compared": int(len(j)), "match_rate_by_statistic": rates,
            "best_matching_statistic": best,
            "bar_spread_label": "indicative (gösterge)",
            "note": "match = |tick statistic − bar spread| ≤ 0.5 point within the same M1 bar"}


def _compare(sym: dict, official: dict, fields: tuple[str, ...]) -> dict[str, Any]:
    have_sym = {f: sym.get(f) for f in fields if sym.get(f) is not None}
    have_off = {f: official.get(f) for f in fields if official.get(f) is not None}
    if not have_sym and not have_off:
        return {"status": MISSING}
    conflicts = {f: {"symbol_info": have_sym[f], "official": have_off[f]} for f in fields
                 if f in have_sym and f in have_off and not np.isclose(float(have_sym[f]), float(have_off[f]))}
    if conflicts:
        status = CONFLICT
    elif have_off and all(f in have_off for f in have_sym) and have_sym:
        status = VERIFIED
    else:
        status = SINGLE_SOURCE
    return {"status": status, "symbol_info": have_sym, "official": have_off,
            "official_source": official.get("source_url"), "official_verified_date": official.get("verified_date"),
            "conflicts": conflicts}


def commission_status(access: dict | None, official: dict, tolerance: float | None) -> dict[str, Any]:
    """D-COMM: deal-derived round-turn median vs official value (with source URL + date).
    Comparison on absolute values (brokers report commission as a negative charge)."""
    agg = (access or {}).get("commission") or {"status": MISSING, "reason": "access probe missing"}
    deal_rt = (agg.get("round_turn_per_lot") or {}).get("median") if agg.get("status") == "MEASURED" else None
    off_val = official.get("commission_per_lot_round_turn")
    off_complete = off_val is not None and bool(official.get("source_url")) and bool(official.get("verified_date"))
    out: dict[str, Any] = {
        "deal_aggregates": agg,
        "official": {"commission_per_lot_round_turn": off_val, "source_url": official.get("source_url"),
                     "verified_date": official.get("verified_date"), "complete": off_complete},
        "tolerance_per_lot": tolerance,
    }
    notes = []
    if off_val is not None and not off_complete:
        notes.append("official value ignored: source_url and verified_date are required")
    sources = int(deal_rt is not None) + int(off_complete)
    if sources == 0:
        out["status"] = MISSING
        out["reason"] = agg.get("reason") if agg.get("status") == MISSING else "NO_ROUND_TURN_AND_NO_OFFICIAL"
    elif sources == 1:
        out["status"] = SINGLE_SOURCE
    elif tolerance is None:
        out["status"] = SINGLE_SOURCE
        notes.append("no commission_match_tolerance configured -> cannot compare")
    else:
        diff = abs(abs(float(deal_rt)) - abs(float(off_val)))
        out["abs_difference_per_lot"] = diff
        out["status"] = VERIFIED if diff <= tolerance else CONFLICT
    out["notes"] = notes
    return out


def evaluate_c5(symbol_info: dict | None, ticks: pd.DataFrame | None, m1: pd.DataFrame | None,
                access: dict | None, official_costs: dict, thresholds: dict, evidence: list[str]) -> CriterionResult:
    si = symbol_info or {}
    point = si.get("point")
    comps = {
        "spread_ticks": spread_distribution(ticks, point),
        "bar_spread_mapping": bar_spread_mapping(ticks, m1, point),
        "commission": commission_status(access, official_costs.get("commission", {}),
                                        thresholds.get("c5", {}).get("commission_match_tolerance")),
        "swap": _compare(si, official_costs.get("swap", {}), SWAP_FIELDS),
        "contract": _compare(si, official_costs.get("contract", {}), CONTRACT_FIELDS),
        "slippage": {"status": MISSING, "note": "no historical fills; Phase 1 uses predefined scenarios"},
    }
    c5 = thresholds.get("c5", {})
    required = c5.get("required_verified", ["commission", "contract"])
    sub = []
    if c5.get("require_spread_from_ticks", True):
        ok = comps["spread_ticks"]["status"] != MISSING
        sub.append({"check": "spread_distribution_from_ticks", "result": PASS if ok else FAIL})
    for name in required:
        st = comps[name]["status"]
        sub.append({"check": f"{name}_verified", "result": PASS if st == VERIFIED else FAIL, "status": st})
    result = FAIL if any(s["result"] == FAIL for s in sub) else PASS
    return CriterionResult("C5", "Maliyet verisinin yeterliliği", result,
                           "Bileşen bazında kaynak durumu; spread tick bid/ask'ten; bar spread eşlemesi ölçülür.",
                           metrics=comps, sub_results=sub, evidence=evidence,
                           notes=["Bar spread alanı gerçek spread varsayılmaz (gösterge)."])


def evaluate_c6(ticks: pd.DataFrame | None, m1: pd.DataFrame | None, point: float | None, thresholds: dict,
                evidence: list[str]) -> CriterionResult:
    method = ("M1 bar OHLC vs tick-derived bid OHLC and ask OHLC within the same minute "
              "(first/max/min/last), tolerance point/2.")
    min_ratio = thresholds.get("extra", {}).get("c6_min_bid_match_ratio")
    notes = ["Bilgi amaçlı (blocking=false). Faz 1: alış girişi ask, alış stop'u bid ile tetiklenir; satış tersi."]
    if ticks is None or m1 is None or _valid_ticks(ticks).empty or m1.empty or not point:
        return CriterionResult("C6", "Bid/ask yürütme hazırlığı", UNKNOWN, method, evidence=evidence,
                               notes=notes, blocking=False)
    t, lo, hi = _tick_bins(ticks, 60)
    tol = point / 2
    out = {}
    bars = m1[(m1["time_server"] >= lo) & (m1["time_server"] <= hi)].set_index("time_server")
    for side in ("bid", "ask"):
        g = t.groupby("bin")[side]
        o = pd.DataFrame({"open": g.first(), "high": g.max(), "low": g.min(), "close": g.last()})
        j = o.join(bars[["open", "high", "low", "close"]], rsuffix="_bar", how="inner")
        if j.empty:
            out[side] = None
            continue
        ok = np.ones(len(j), dtype=bool)
        per = {}
        for c in ("open", "high", "low", "close"):
            m = (np.abs(j[c] - j[f"{c}_bar"]) <= tol).to_numpy()
            per[c] = float(m.mean())
            ok &= m
        out[side] = {"bars_compared": int(len(j)), "all_fields_match_ratio": float(ok.mean()), "per_field": per}
    metrics = {"comparison": out, "threshold_min_bid_match_ratio": min_ratio}
    if not out.get("bid"):
        return CriterionResult("C6", "Bid/ask yürütme hazırlığı", UNKNOWN, method, metrics, evidence=evidence,
                               notes=notes, blocking=False)
    if min_ratio is None:
        res = UNKNOWN
    else:
        res = PASS if out["bid"]["all_fields_match_ratio"] >= min_ratio else FAIL
    return CriterionResult("C6", "Bid/ask yürütme hazırlığı", res, method, metrics, evidence=evidence,
                           notes=notes, blocking=False)
