"""Aggregate commission statistics from deal history (decisions D-COMM, D-COMM2).

Fields read in memory: symbol, type, entry, volume, commission, fee (if the
terminal provides it), position_id (grouping only, never returned) and time
(first/last deal day only). Output holds aggregates only — no ticket, price,
profit, per-deal row, amount of non-symbol deals or timestamp list.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from statistics import median
from typing import Any

# MT5 enums. ENUM_DEAL_TYPE: BUY=0, SELL=1. ENUM_DEAL_ENTRY: IN=0, OUT=1, INOUT=2, OUT_BY=3.
DEAL_TYPE_BUY, DEAL_TYPE_SELL = 0, 1
ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY = 0, 1, 2, 3

MISSING = "MISSING"
MEASURED = "MEASURED"
SUSPECT_ZERO = "SUSPECT_ZERO"
NO_DEALS = "NO_DEALS"
ACCESS_DENIED = "ACCESS_DENIED"


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, "median": None, "min": None, "max": None}
    return {"n": len(values), "median": median(values), "min": min(values), "max": max(values)}


def _components(comm: list[float], fee: list[float] | None) -> dict[str, Any]:
    total = comm if fee is None else [c + f for c, f in zip(comm, fee, strict=True)]
    return {"commission": _stats(comm),
            "fee": {"status": MISSING, "reason": "deal has no fee field"} if fee is None else _stats(fee),
            "total": _stats(total)}


def _day(server_epoch: int) -> str:
    return datetime.fromtimestamp(int(server_epoch), tz=UTC).strftime("%Y-%m-%d")


def aggregate_commission(deals: Any, symbol: str, window_days: int, last_error: Any = None) -> dict[str, Any]:
    base = {"window_days": window_days, "symbol": symbol,
            "unit": "account currency per lot, sign as reported by broker (negative = charge)"}
    if deals is None:
        return {**base, "status": MISSING, "reason": ACCESS_DENIED,
                "detail": f"history_deals_get returned None (last_error={last_error!r})"}
    # Diagnostic: type -> count of deals without a symbol (commission may be booked as a separate deal type).
    no_symbol_types = Counter(str(int(d.type)) for d in deals if not getattr(d, "symbol", ""))
    base["no_symbol_deal_type_counts"] = dict(sorted(no_symbol_types.items()))
    sym = [d for d in deals if getattr(d, "symbol", None) == symbol]
    if not sym:
        return {**base, "status": MISSING, "reason": NO_DEALS,
                "detail": f"{len(deals)} deals in window, none for {symbol}"}

    has_fee = "fee" in sym[0]._fields
    trade = [d for d in sym if int(d.type) in (DEAL_TYPE_BUY, DEAL_TYPE_SELL)]
    side: dict[int, dict[str, list[float]]] = {e: {"comm": [], "fee": []} for e in (ENTRY_IN, ENTRY_OUT)}
    pos: dict[int, dict[str, Any]] = defaultdict(lambda: {"in_vol": 0.0, "out_vol": 0.0, "comm": 0.0,
                                                          "fee": 0.0, "mixed": False})
    other_entry = zero_volume = 0
    for d in trade:
        vol, entry = float(d.volume), int(d.entry)
        comm, fee = float(d.commission), float(d.fee) if has_fee else 0.0
        acc = pos[int(d.position_id)]
        if entry in (ENTRY_INOUT, ENTRY_OUT_BY):
            acc["mixed"] = True
            other_entry += 1
            continue
        if entry not in side or vol <= 0:
            zero_volume += int(vol <= 0)
            other_entry += int(entry not in side)
            continue
        side[entry]["comm"].append(comm / vol)
        side[entry]["fee"].append(fee / vol)
        acc["comm"] += comm
        acc["fee"] += fee
        acc["in_vol" if entry == ENTRY_IN else "out_vol"] += vol
    excluded_mixed = sum(1 for a in pos.values() if a["mixed"])
    closed = [a for a in pos.values()
              if not a["mixed"] and a["in_vol"] > 0 and abs(a["in_vol"] - a["out_vol"]) < 1e-9]
    rt_comm = [a["comm"] / a["in_vol"] for a in closed]
    rt_fee = [a["fee"] / a["in_vol"] for a in closed]
    del pos  # position ids never leave this function

    measured_totals = [c + f for e in side for c, f in zip(side[e]["comm"], side[e]["fee"], strict=True)]
    per_side = {name: _components(side[e]["comm"], side[e]["fee"] if has_fee else None)
                for name, e in (("IN", ENTRY_IN), ("OUT", ENTRY_OUT))}
    out = {
        **base,
        "fee_field_present": has_fee,
        "deals_for_symbol": len(sym),
        "excluded_non_trade_type": len(sym) - len(trade),
        "excluded_other_entry_or_zero_volume": other_entry + zero_volume,
        "round_turn_excluded_positions_inout_or_out_by": excluded_mixed,
        "per_side_per_lot": per_side,
        "round_turn_per_lot": _components(rt_comm, rt_fee if has_fee else None),
        "per_side_total_per_lot_all": _stats(measured_totals),
        "round_turn_note": "positions fully closed in window, no INOUT/OUT_BY deal: (sum IN+OUT) / IN volume",
        "first_deal_day_server": _day(min(int(d.time) for d in sym)),
        "last_deal_day_server": _day(max(int(d.time) for d in sym)),
    }
    if measured_totals and all(v == 0 for v in measured_totals):
        out["status"] = SUSPECT_ZERO
        out["reason"] = ("all measured commission+fee values are 0 — commission may be booked as a separate "
                         "deal type or another field; see no_symbol_deal_type_counts")
    elif not measured_totals:
        out["status"] = MISSING
        out["reason"] = "NO_TRADE_DEALS"
    else:
        out["status"] = MEASURED
    return out
