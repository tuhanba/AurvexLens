"""Raw data extraction (P0.4, P0.5, P0.7 + live probes for C3/C4).

Must only run after identity verification passed on the same connection.
All timestamps passed to MT5 are server-time epoch values wrapped in
tz-aware UTC datetimes (the MetaTrader5 package compares them numerically
with the server-time `time` fields); nothing here is real UTC except the
local system clock readings, which are explicitly named `system_utc_*`.
"""

from __future__ import annotations

import calendar
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from aurvex_lens.bridge.mt5_readonly import ReadOnlyMT5
from aurvex_lens.common.config import LensConfig
from aurvex_lens.common.provenance import environment_versions, to_jsonable, utc_iso
from aurvex_lens.data.schema import TF_MINUTES, rates_to_frame, ticks_to_frame
from aurvex_lens.data.snapshot import SnapshotWriter

DAY = 86_400


def server_dt(epoch_server: int | float) -> datetime:
    """Wrap a server-time epoch for MT5 range calls (NOT a UTC conversion)."""
    return datetime.fromtimestamp(epoch_server, tz=UTC)


def extract_rates(mt5: ReadOnlyMT5, symbol: str, tf: str, chunk: int, max_bars: int) -> tuple[pd.DataFrame, dict]:
    tf_code = mt5.timeframe(tf)
    parts: list[np.ndarray] = []
    pos = 0
    calls = 0
    stop_reason = ""
    last_error = None
    while True:
        arr = mt5.copy_rates_from_pos(symbol, tf_code, pos, chunk)
        calls += 1
        if arr is None:
            last_error = mt5.last_error()
            stop_reason = "copy_rates_from_pos returned None"
            break
        if len(arr) == 0:
            stop_reason = "empty chunk"
            break
        parts.append(arr)
        pos += len(arr)
        if len(arr) < chunk:
            stop_reason = "short chunk (oldest available bar reached)"
            break
        if pos >= max_bars:
            stop_reason = f"rates_max_bars={max_bars} reached"
            break
    frames = [rates_to_frame(a) for a in reversed(parts)]
    df = pd.concat(frames, ignore_index=True) if frames else rates_to_frame(None)
    n_before = len(df)
    df = df.drop_duplicates(subset="time_server").sort_values("time_server").reset_index(drop=True)
    info = {
        "kind": "rates", "symbol": symbol, "timeframe": tf, "method": "copy_rates_from_pos paging from pos 0 backwards",
        "requested_range": f"pos 0 .. oldest available (chunk={chunk}, cap={max_bars})",
        "calls": calls, "stop_reason": stop_reason, "last_error_at_stop": to_jsonable(last_error),
        "duplicates_dropped": n_before - len(df),
    }
    return df, info


def probe_windows(latest_server: int, max_months: int) -> list[tuple[int, int]]:
    """1h window on the first Wednesday of each month, 14:00 server time,
    going back from the month of `latest_server`. Future windows skipped."""
    d = datetime.fromtimestamp(latest_server, tz=UTC)
    y, m = d.year, d.month
    out = []
    for _ in range(max_months):
        first_wd = calendar.weekday(y, m, 1)  # Mon=0
        day = 1 + (2 - first_wd) % 7  # Wednesday=2
        start = calendar.timegm((y, m, day, 14, 0, 0))
        if start + 3600 <= latest_server:
            out.append((start, start + 3600))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def probe_ticks(mt5: ReadOnlyMT5, symbol: str, latest_server: int, max_months: int,
                stop_after_empty: int) -> tuple[pd.DataFrame, list[dict]]:
    probes = []
    frames = []
    found_any = False
    empty_run = 0
    for start, end in probe_windows(latest_server, max_months):
        arr = mt5.copy_ticks_range(symbol, server_dt(start), server_dt(end), mt5.copy_ticks_all)
        n = 0 if arr is None else len(arr)
        rec = {"window_start_server": start, "window_end_server": end, "ticks": n}
        if arr is None:
            rec["last_error"] = to_jsonable(mt5.last_error())
        probes.append(rec)
        if n:
            found_any = True
            empty_run = 0
            frames.append(ticks_to_frame(arr))
        elif found_any:
            empty_run += 1
            if empty_run >= stop_after_empty:
                break
    frames.reverse()
    df = pd.concat(frames, ignore_index=True) if frames else ticks_to_frame(None)
    return df.sort_values("time_msc_server", kind="stable").reset_index(drop=True), probes


def extract_recent_ticks(mt5: ReadOnlyMT5, symbol: str, latest_server: int, days: int) -> tuple[pd.DataFrame, dict]:
    end_day = (latest_server // DAY + 1) * DAY
    start_day = end_day - days * DAY
    frames = []
    per_day = []
    for d0 in range(start_day, end_day, DAY):
        arr = mt5.copy_ticks_range(symbol, server_dt(d0), server_dt(d0 + DAY - 1), mt5.copy_ticks_all)
        n = 0 if arr is None else len(arr)
        per_day.append({"day_start_server": d0, "ticks": n})
        if n:
            frames.append(ticks_to_frame(arr))
    df = pd.concat(frames, ignore_index=True) if frames else ticks_to_frame(None)
    n_before = len(df)
    df = df.drop_duplicates().sort_values("time_msc_server", kind="stable").reset_index(drop=True)
    info = {"kind": "ticks_recent", "symbol": symbol, "method": "copy_ticks_range per server day, COPY_TICKS_ALL",
            "requested_range": f"server days [{start_day}, {end_day})", "per_day": per_day,
            "duplicates_dropped": n_before - len(df)}
    return df, info


def windows_clock_status(runner: Callable[[list[str]], str] | None = None) -> dict[str, Any]:
    """Local clock sync status via `w32tm /query /status` (read-only query)."""
    if runner is None:
        if sys.platform != "win32":
            return {"status": "UNKNOWN", "reason": "not running on Windows", "raw": None}

        def runner(cmd: list[str]) -> str:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False).stdout

    try:
        raw = runner(["w32tm", "/query", "/status"])
    except Exception as e:  # noqa: BLE001
        return {"status": "UNKNOWN", "reason": f"w32tm failed: {e}", "raw": None}
    fields = {}
    for line in (raw or "").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    leap = fields.get("Leap Indicator")
    source = fields.get("Source")
    if leap is None or source is None:
        return {"status": "UNKNOWN", "reason": "w32tm output not parseable (localized?); see raw", "raw": raw,
                "fields": fields}
    unsynced_sources = ("local cmos clock", "free-running system clock")
    synced = leap.startswith("0") and source.lower() not in unsynced_sources
    return {"status": "SYNCED" if synced else "NOT_SYNCED", "raw": raw, "fields": fields}


def live_probe(mt5: ReadOnlyMT5, symbol: str, samples: int, sleep: Callable[[float], None]) -> dict[str, Any]:
    out = []
    for i in range(samples):
        sys_ms = int(time.time() * 1000)
        tick = mt5.symbol_info_tick(symbol)
        ti = mt5.terminal_info()
        out.append({
            "system_utc_ms": sys_ms,
            "tick_time_msc_server": None if tick is None else int(tick.time_msc),
            "bid": None if tick is None else float(tick.bid),
            "ask": None if tick is None else float(tick.ask),
            "terminal_connected": None if ti is None else bool(getattr(ti, "connected", None)),
        })
        if i < samples - 1:
            sleep(1.0)
    return {"samples": out, "note": "system_utc_ms = local system clock; tick time is server time (not UTC)"}


def access_probe(mt5: ReadOnlyMT5, symbol: str, now_server: int) -> dict[str, Any]:
    """P0.7 — counts and field names only; deal contents are not stored."""
    frm, to = server_dt(946_684_800), server_dt(now_server + DAY)  # 2000-01-01 .. now+1d
    total = mt5.history_deals_total(frm, to)
    deals = mt5.history_deals_get(frm, to)
    res: dict[str, Any] = {
        "history_deals_total": to_jsonable(total),
        "history_deals_total_error": None if total is not None else to_jsonable(mt5.last_error()),
        "history_deals_get_returned": "None" if deals is None else f"{len(deals)} records",
        "history_deals_get_error": None if deals is not None else to_jsonable(mt5.last_error()),
        "deal_field_names": list(deals[0]._fields) if deals else [],
    }
    if deals:
        sym_deals = [d for d in deals if getattr(d, "symbol", None) == symbol]
        res["deals_for_symbol_count"] = len(sym_deals)
        res["commission_field_present"] = "commission" in deals[0]._fields
        res["deals_for_symbol_nonzero_commission_count"] = (
            sum(1 for d in sym_deals if getattr(d, "commission", 0)) if res["commission_field_present"] else None)
    pt = mt5.positions_total()
    res["positions_total"] = to_jsonable(pt)
    res["note"] = "Only counts and field names are recorded; no deal/position contents."
    return res


def symbol_snapshot(mt5: ReadOnlyMT5, symbol: str) -> dict[str, Any]:
    info = mt5.symbol_info(symbol)
    letters = "".join(ch for ch in symbol if ch.isalpha())[:3] or symbol
    group = f"*{letters}*"
    syms = mt5.symbols_get(group)
    return {
        "configured_symbol": symbol,
        "symbol_found": info is not None,
        "symbol_info": to_jsonable(info) if info is not None else None,
        "symbol_info_error": None if info is not None else to_jsonable(mt5.last_error()),
        "symbols_get_group": group,
        "matching_symbol_names": [s.name for s in syms] if syms else [],
        "tick_at_snapshot": to_jsonable(mt5.symbol_info_tick(symbol)),
    }


def run_extraction(mt5: ReadOnlyMT5, cfg: LensConfig, identity: dict[str, Any], extraction_id: str,
                   data_origin: str, sleep: Callable[[float], None] = time.sleep,
                   clock_runner: Callable[[list[str]], str] | None = None) -> SnapshotWriter:
    started = utc_iso()
    writer = SnapshotWriter(cfg.data_dir, extraction_id, data_origin)
    ti = mt5.terminal_info()
    writer.write_json("identity.json", identity)

    sym = symbol_snapshot(mt5, cfg.symbol)
    writer.write_json("symbol_snapshot.json", sym)
    if not sym["symbol_found"]:
        writer.finalize({"status": "ABORTED_SYMBOL_NOT_FOUND", "extraction_started_utc": started})
        return writer

    writer.write_json("clock_status.json", windows_clock_status(clock_runner))
    writer.write_json("live_probe.json", live_probe(mt5, cfg.symbol, cfg.live_probe_samples, sleep))

    maxbars = getattr(ti, "maxbars", None)
    for tf in cfg.timeframes:
        if tf not in TF_MINUTES:
            raise ValueError(f"unsupported timeframe {tf}")
        df, info = extract_rates(mt5, cfg.symbol, tf, cfg.rates_chunk, cfg.rates_max_bars)
        info["terminal_maxbars"] = maxbars
        info["possibly_capped_by_maxbars"] = (maxbars is not None and len(df) >= int(maxbars))
        writer.write_parquet(f"rates_{tf}.parquet", df, info)

    tick = mt5.symbol_info_tick(cfg.symbol)
    latest = int(tick.time) if tick is not None else None
    if latest is None:
        writer.write_json("tick_probes.json", {"status": "UNKNOWN", "reason": "symbol_info_tick returned None"})
    else:
        tp_df, probes = probe_ticks(mt5, cfg.symbol, latest, cfg.tick_probe_max_months,
                                    cfg.tick_probe_stop_after_empty)
        writer.write_json("tick_probes.json", {
            "method": "1h window, first Wednesday of each month, 14:00-15:00 server time, COPY_TICKS_ALL",
            "stop_rule": f"after {cfg.tick_probe_stop_after_empty} consecutive empty months once data found, "
                         f"or {cfg.tick_probe_max_months} months",
            "probes": probes})
        writer.write_parquet("ticks_probe.parquet", tp_df, {"kind": "ticks_probe", "symbol": cfg.symbol})
        rt_df, rt_info = extract_recent_ticks(mt5, cfg.symbol, latest, cfg.tick_full_days)
        writer.write_parquet("ticks_recent.parquet", rt_df, rt_info)

    writer.write_json("access_probe.json", access_probe(mt5, cfg.symbol, latest or int(time.time())))

    writer.finalize({
        "status": "COMPLETE",
        "extraction_started_utc": started,
        "extraction_finished_utc": utc_iso(),
        "terminal_build": getattr(ti, "build", None),
        "terminal_version": to_jsonable(mt5.version()),
        "versions": environment_versions(),
        "symbol": cfg.symbol,
        "timeframes": list(cfg.timeframes),
    })
    return writer
