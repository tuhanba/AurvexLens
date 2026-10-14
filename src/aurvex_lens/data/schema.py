"""Column schemas for raw snapshots.

MT5 `time` is BROKER SERVER TIME expressed as epoch seconds — it is NOT UTC.
It is therefore stored as `time_server`. A `time_utc` column may only be
derived after the server-time rule (open decision O3) is approved.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RATE_COLUMNS = ["time_server", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
TICK_COLUMNS = ["time_server", "bid", "ask", "last", "volume", "time_msc_server", "flags", "volume_real"]

TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}


def rates_to_frame(arr: np.ndarray | None) -> pd.DataFrame:
    if arr is None or len(arr) == 0:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in RATE_COLUMNS}).astype(
            {"time_server": "int64", "tick_volume": "int64", "spread": "int64", "real_volume": "int64"})
    df = pd.DataFrame(arr)
    df = df.rename(columns={"time": "time_server"})
    missing = [c for c in RATE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"rates array missing columns: {missing}")
    df = df[RATE_COLUMNS].astype({"time_server": "int64", "tick_volume": "int64",
                                   "spread": "int64", "real_volume": "int64"})
    return df


def ticks_to_frame(arr: np.ndarray | None) -> pd.DataFrame:
    if arr is None or len(arr) == 0:
        return pd.DataFrame({c: pd.Series(dtype="float64") for c in TICK_COLUMNS}).astype(
            {"time_server": "int64", "time_msc_server": "int64", "flags": "int64", "volume": "int64"})
    df = pd.DataFrame(arr).rename(columns={"time": "time_server", "time_msc": "time_msc_server"})
    missing = [c for c in TICK_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"ticks array missing columns: {missing}")
    return df[TICK_COLUMNS].astype({"time_server": "int64", "time_msc_server": "int64",
                                    "flags": "int64", "volume": "int64"})
