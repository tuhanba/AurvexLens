"""C1 — history coverage per timeframe + tick coverage probe summary."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from aurvex_lens.quality.result import FAIL, PASS, UNKNOWN, CriterionResult, combine

DAYS_PER_MONTH = 30.4375


def server_iso(epoch_server: int | None) -> str | None:
    """Format a server-time epoch. The result is SERVER time, not UTC."""
    if epoch_server is None:
        return None
    return datetime.fromtimestamp(int(epoch_server), tz=UTC).strftime("%Y-%m-%d %H:%M (server)")


def tf_coverage(tf: str, df: pd.DataFrame | None, file_info: dict | None, min_months: float | None,
                gap_info: dict | None) -> dict[str, Any]:
    if df is None:
        return {"timeframe": tf, "result": UNKNOWN, "reason": "timeframe not in snapshot"}
    if df.empty:
        return {"timeframe": tf, "result": FAIL, "rows": 0, "reason": "no bars returned"}
    first, last = int(df["time_server"].iloc[0]), int(df["time_server"].iloc[-1])
    days = (last - first) / 86400
    months = days / DAYS_PER_MONTH
    out: dict[str, Any] = {
        "timeframe": tf, "rows": int(len(df)),
        "first_bar_server": server_iso(first), "last_bar_server": server_iso(last),
        "span_days": round(days, 2), "span_months": round(months, 2),
        "min_months_threshold": min_months,
    }
    if gap_info is not None:
        out["expected_bars_trading_hours"] = gap_info.get("expected_bars")
        exp = gap_info.get("expected_bars") or 0
        out["completeness_ratio"] = round(len(df) / exp, 6) if exp else None
        out["expected_bars_note"] = ("rows + missing slots outside (candidate/confirmed) closures; "
                                     "depends on unconfirmed closure candidates")
    capped = bool(file_info and file_info.get("possibly_capped_by_maxbars"))
    out["possibly_capped_by_maxbars"] = capped
    if min_months is None:
        out["result"] = UNKNOWN
        out["reason"] = "no threshold configured"
    else:
        out["result"] = PASS if months >= min_months else FAIL
        if out["result"] == FAIL and capped:
            out["reason"] = ("row count reached terminal 'Max bars in chart'; history may be truncated by "
                             "terminal setting (Phase 0 does not change terminal settings)")
    return out


def tick_coverage(probes_doc: dict | None, ticks_probe: pd.DataFrame | None) -> dict[str, Any]:
    if not probes_doc or "probes" not in probes_doc:
        return {"status": UNKNOWN, "reason": "no tick probes in snapshot"}
    probes = probes_doc["probes"]
    found = [p for p in probes if p["status"] == "TICKS_FOUND"]
    by_status: dict[str, int] = {}
    for p in probes:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1
    return {
        "method": probes_doc.get("method"), "stop_rule": probes_doc.get("stop_rule"),
        "months_probed": len(probes), "months_by_status": by_status,
        "months_found_on_retry": sum(1 for p in found if p.get("retry_used")),
        "earliest_month_with_ticks": min((p["month"] for p in found), default=None),
        "earliest_window_with_ticks_server": server_iso(min((p["window_start_server"] for p in found), default=None)),
        "per_month": [{"month": p["month"], "status": p["status"], "ticks": p["ticks"],
                       "attempts": len(p["attempts"])} for p in probes],
        "probe_ticks_rows": 0 if ticks_probe is None else int(len(ticks_probe)),
        "note": "Earliest accessible tick date has ±1 month resolution. No threshold.",
    }


def evaluate_c1(frames: dict[str, pd.DataFrame | None], file_infos: dict[str, dict], thresholds: dict,
                gap_infos: dict[str, dict], probes_doc: dict | None, ticks_probe: pd.DataFrame | None,
                evidence: list[str]) -> CriterionResult:
    mins = thresholds.get("c1", {}).get("min_months", {})
    subs = [tf_coverage(tf, frames.get(tf), file_infos.get(tf), mins.get(tf), gap_infos.get(tf))
            for tf in ("H1", "M15", "M5", "M1")]
    res = combine([s["result"] for s in subs])
    return CriterionResult(
        id="C1", title="Geçmiş kapsamı", result=res,
        method=("Her TF için ilk/son bar (server time), takvim süresi (gün/30.4375 = ay) ve eşik karşılaştırması. "
                "Beklenen bar = satır + kapanış dışı eksik slotlar. Tick: aylık 1 saatlik pencere sondajı."),
        sub_results=subs, metrics={"ticks": tick_coverage(probes_doc, ticks_probe)}, evidence=evidence,
    )
