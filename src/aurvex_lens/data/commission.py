"""Aggregate commission statistics from deal history (decision D-COMM).

Only `symbol`, `volume`, `entry`, `commission`, `position_id` are read from
each deal, in memory. `position_id` is used only for grouping and is never
returned. The output holds aggregates only — no ticket, price, profit,
per-deal row or timestamp list — plus the first/last deal day (server date).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from statistics import median
from typing import Any

# MT5 ENUM_DEAL_ENTRY values (DEAL_ENTRY_IN / DEAL_ENTRY_OUT).
ENTRY_IN = 0
ENTRY_OUT = 1

MISSING = "MISSING"
MEASURED = "MEASURED"
NO_DEALS = "NO_DEALS"
ACCESS_DENIED = "ACCESS_DENIED"


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {"n": len(values), "median": median(values), "min": min(values), "max": max(values)}


def _day(server_epoch: int) -> str:
    return datetime.fromtimestamp(int(server_epoch), tz=UTC).strftime("%Y-%m-%d")


def aggregate_commission(deals: Any, symbol: str, window_days: int, last_error: Any = None) -> dict[str, Any]:
    base = {"window_days": window_days, "symbol": symbol,
            "unit": "account currency per lot, sign as reported by broker (negative = charge)"}
    if deals is None:
        return {**base, "status": MISSING, "reason": ACCESS_DENIED,
                "detail": f"history_deals_get returned None (last_error={last_error!r})"}
    sym = [d for d in deals if getattr(d, "symbol", None) == symbol]
    if not sym:
        return {**base, "status": MISSING, "reason": NO_DEALS,
                "detail": f"{len(deals)} deals in window, none for {symbol}"}

    per_side: dict[int, list[float]] = {ENTRY_IN: [], ENTRY_OUT: []}
    other_entries = 0
    by_pos: dict[int, dict[str, float]] = defaultdict(lambda: {"in_vol": 0.0, "out_vol": 0.0, "comm": 0.0})
    times = []
    for d in sym:
        vol, entry, comm, pos = float(d.volume), int(d.entry), float(d.commission), int(d.position_id)
        times.append(int(d.time))
        if entry not in per_side or vol <= 0:
            other_entries += 1
            continue
        per_side[entry].append(comm / vol)
        acc = by_pos[pos]
        acc["comm"] += comm
        acc["in_vol" if entry == ENTRY_IN else "out_vol"] += vol
    round_turn = [a["comm"] / a["in_vol"] for a in by_pos.values()
                  if a["in_vol"] > 0 and abs(a["in_vol"] - a["out_vol"]) < 1e-9]
    del by_pos  # position ids never leave this function
    return {
        **base, "status": MEASURED,
        "deals_for_symbol": len(sym),
        "per_side_per_lot": {"IN": _stats(per_side[ENTRY_IN]), "OUT": _stats(per_side[ENTRY_OUT])},
        "round_turn_per_lot": _stats(round_turn),
        "round_turn_note": "positions fully closed in window: (sum of IN+OUT commission) / IN volume",
        "excluded_other_entry_or_zero_volume": other_entries,
        "first_deal_day_server": _day(min(times)),
        "last_deal_day_server": _day(max(times)),
    }
