"""Provenance helpers: ids, hashes, versions, timestamps."""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

SYNTHETIC_LABEL = "SYNTHETIC — NOT MARKET DATA"
LIVE_LABEL = "CANLI VERİ"


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def new_run_id(prefix: str = "") -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}{stamp}_{secrets.token_hex(3)}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pkg_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "NOT_INSTALLED"


def environment_versions() -> dict[str, str]:
    return {
        "python": sys.version.split()[0],
        "aurvex_lens": pkg_version("aurvex-lens"),
        "MetaTrader5": pkg_version("MetaTrader5"),
        "pandas": pkg_version("pandas"),
        "pyarrow": pkg_version("pyarrow"),
        "numpy": pkg_version("numpy"),
    }


def to_jsonable(obj: Any) -> Any:
    """Convert MT5 named tuples / numpy scalars to JSON-safe values."""
    if hasattr(obj, "_asdict"):
        return {k: to_jsonable(v) for k, v in obj._asdict().items()}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if hasattr(obj, "item") and callable(obj.item):  # numpy scalar
        return obj.item()
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def dumps(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), indent=2, ensure_ascii=False, sort_keys=False)
