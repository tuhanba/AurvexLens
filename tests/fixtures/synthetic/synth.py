"""SYNTHETIC — NOT MARKET DATA. Deterministic generator for tests (see README.md)."""

from __future__ import annotations

import calendar
from functools import lru_cache

import numpy as np
import pandas as pd

SYNTHETIC_LABEL = "SYNTHETIC — NOT MARKET DATA"
POINT = 0.001
START = calendar.timegm((2026, 2, 23, 0, 0, 0))  # Monday, server time
END = calendar.timegm((2026, 4, 11, 0, 0, 0))  # Saturday 00:00, exclusive
GAP_START = calendar.timegm((2026, 3, 18, 10, 0, 0))
GAP_END = calendar.timegm((2026, 3, 18, 10, 45, 0))
HOLIDAY = calendar.timegm((2026, 4, 3, 0, 0, 0))
SPIKE = calendar.timegm((2026, 3, 6, 15, 30, 0))
TICK_SECONDS = (5, 25, 45)


def open_minutes() -> np.ndarray:
    m = np.arange(START, END, 60, dtype="int64")
    dow = ((m // 86400) + 3) % 7  # Mon=0
    mod = (m % 86400) // 60
    is_open = (dow <= 4) & (mod >= 60)
    is_open &= ~((m >= GAP_START) & (m < GAP_END))
    is_open &= ~((m >= HOLIDAY) & (m < HOLIDAY + 86400))
    return m[is_open]


@lru_cache(maxsize=1)
def ticks() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    mins = open_minutes()
    t = (mins[:, None] + np.array(TICK_SECONDS)[None, :]).ravel()
    steps = rng.normal(0, 2, len(t)).round() * POINT
    spike = (t >= SPIKE) & (t < SPIKE + 60)
    steps[spike] += 0.15
    bid = np.round(30.0 + np.cumsum(steps), 3)
    hour = (t // 3600) % 24
    spread_pts = np.where((hour == 1) | (hour == 23), 40, 20) + rng.integers(0, 5, len(t))
    ask = np.round(bid + spread_pts * POINT, 3)
    return pd.DataFrame({
        "time": t, "bid": bid, "ask": ask, "last": 0.0, "volume": 0,
        "time_msc": t * 1000, "flags": 6, "volume_real": 0.0,
    })


@lru_cache(maxsize=1)
def m1() -> pd.DataFrame:
    tk = ticks()
    b = tk["time"] - tk["time"] % 60
    g = tk.groupby(b)
    sp = ((tk["ask"] - tk["bid"]) / POINT).round().astype("int64")
    out = pd.DataFrame({
        "time": g["time"].first() - g["time"].first() % 60,
        "open": g["bid"].first(), "high": g["bid"].max(), "low": g["bid"].min(), "close": g["bid"].last(),
        "tick_volume": g.size().astype("int64"), "spread": sp.groupby(b).first(), "real_volume": 0,
    })
    return out.reset_index(drop=True)


@lru_cache(maxsize=4)
def bars(tf_min: int) -> pd.DataFrame:
    base = m1()
    if tf_min == 1:
        return base
    sec = tf_min * 60
    b = base["time"] - base["time"] % sec
    g = base.groupby(b)
    out = pd.DataFrame({
        "time": b.groupby(b).first(), "open": g["open"].first(), "high": g["high"].max(),
        "low": g["low"].min(), "close": g["close"].last(), "tick_volume": g["tick_volume"].sum(),
        "spread": g["spread"].first(), "real_volume": 0,
    })
    return out.reset_index(drop=True)


def to_rates_array(df: pd.DataFrame) -> np.ndarray:
    dt = np.dtype([("time", "<i8"), ("open", "<f8"), ("high", "<f8"), ("low", "<f8"), ("close", "<f8"),
                   ("tick_volume", "<u8"), ("spread", "<i4"), ("real_volume", "<u8")])
    arr = np.empty(len(df), dtype=dt)
    for c in dt.names:
        arr[c] = df[c].to_numpy()
    return arr


def to_ticks_array(df: pd.DataFrame) -> np.ndarray:
    dt = np.dtype([("time", "<i8"), ("bid", "<f8"), ("ask", "<f8"), ("last", "<f8"), ("volume", "<u8"),
                   ("time_msc", "<i8"), ("flags", "<u4"), ("volume_real", "<f8")])
    arr = np.empty(len(df), dtype=dt)
    for c in dt.names:
        arr[c] = df[c].to_numpy()
    return arr
