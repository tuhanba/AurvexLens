"""Immutable raw snapshots (spec §5 snapshot rule).

Every extraction gets a new folder `data/raw/<extraction_id>/`. Files are
created with exclusive mode ('x'): an existing file is never overwritten.
`meta.json` is written last and lists every file with its sha256.
"""

from __future__ import annotations

import io
import json
import os
import stat
from pathlib import Path
from typing import Any

import pandas as pd

from aurvex_lens.common.provenance import dumps, sha256_bytes, sha256_file

ORIGIN_LIVE = "LIVE_MT5"
ORIGIN_SYNTHETIC = "SYNTHETIC"


class SnapshotError(Exception):
    pass


class SnapshotWriter:
    def __init__(self, data_dir: Path, extraction_id: str, data_origin: str) -> None:
        if data_origin not in (ORIGIN_LIVE, ORIGIN_SYNTHETIC):
            raise ValueError(data_origin)
        self.extraction_id = extraction_id
        self.data_origin = data_origin
        self.dir = Path(data_dir) / "raw" / extraction_id
        self.dir.parent.mkdir(parents=True, exist_ok=True)
        self.dir.mkdir(exist_ok=False)  # never reuse an extraction folder
        self.files: list[dict[str, Any]] = []
        self._finalized = False
        self.status: str | None = None

    def _write_bytes(self, name: str, data: bytes) -> str:
        if self._finalized:
            raise SnapshotError("snapshot already finalized")
        path = self.dir / name
        with open(path, "xb") as f:  # exclusive create: refuses to overwrite
            f.write(data)
        return sha256_bytes(data)

    def write_parquet(self, name: str, df: pd.DataFrame, info: dict[str, Any]) -> dict[str, Any]:
        buf = io.BytesIO()
        df.to_parquet(buf, engine="pyarrow", index=False)
        digest = self._write_bytes(name, buf.getvalue())
        entry = {"file": name, "sha256": digest, "rows": int(len(df)), **info}
        if "time_server" in df.columns and len(df):
            entry["first_time_server"] = int(df["time_server"].iloc[0])
            entry["last_time_server"] = int(df["time_server"].iloc[-1])
        self.files.append(entry)
        return entry

    def write_json(self, name: str, obj: Any, info: dict[str, Any] | None = None) -> dict[str, Any]:
        digest = self._write_bytes(name, dumps(obj).encode("utf-8"))
        entry = {"file": name, "sha256": digest, **(info or {})}
        self.files.append(entry)
        return entry

    def finalize(self, meta: dict[str, Any]) -> Path:
        full = {
            "extraction_id": self.extraction_id,
            "data_origin": self.data_origin,
            **meta,
            "time_column_note": "time_server = broker server time (epoch seconds), NOT UTC",
            "files": self.files,
        }
        self._write_bytes("meta.json", dumps(full).encode("utf-8"))
        self._finalized = True
        self.status = full.get("status")
        for p in self.dir.iterdir():
            os.chmod(p, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
        return self.dir


def load_meta(snapshot_dir: Path) -> dict[str, Any]:
    with open(Path(snapshot_dir) / "meta.json", encoding="utf-8") as f:
        return json.load(f)


def verify_snapshot(snapshot_dir: Path) -> list[dict[str, Any]]:
    """Recompute sha256 of every listed file. Returns per-file results."""
    meta = load_meta(snapshot_dir)
    out = []
    for entry in meta["files"]:
        p = Path(snapshot_dir) / entry["file"]
        actual = sha256_file(p) if p.exists() else "MISSING"
        out.append({"file": entry["file"], "expected": entry["sha256"], "actual": actual,
                    "ok": actual == entry["sha256"]})
    return out


def latest_snapshot(data_dir: Path) -> Path:
    raw = Path(data_dir) / "raw"
    dirs = sorted(p for p in raw.iterdir()
                  if (p / "meta.json").exists() and load_meta(p).get("status") == "COMPLETE") if raw.exists() else []
    if not dirs:
        raise SnapshotError(f"no COMPLETE snapshot under {raw}")
    return dirs[-1]
