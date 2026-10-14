"""Configuration loading (config/local.toml, never committed)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

DEFAULT_CONFIG = Path("config/local.toml")
DEFAULT_THRESHOLDS = Path("config/quality_thresholds.toml")


class ConfigError(Exception):
    pass


def normalize_win_path(p: str) -> str:
    """Case-insensitive, separator-normalized Windows path for comparison."""
    s = str(p).strip().strip('"').replace("/", "\\").rstrip("\\")
    return str(PureWindowsPath(s)).lower()


def terminal_dir(terminal_path: str) -> str:
    """`...\\terminal64.exe` -> its folder (what terminal_info().path reports)."""
    norm = normalize_win_path(terminal_path)
    if norm.endswith(".exe"):
        return str(PureWindowsPath(norm).parent)
    return norm


@dataclass(frozen=True)
class LensConfig:
    terminal_path: str
    forbidden_terminal_paths: tuple[str, ...]
    expected_login: int
    expected_server: str
    symbol: str
    timeframes: tuple[str, ...] = ("H1", "M15", "M5", "M1")
    data_dir: Path = Path("data")
    rates_chunk: int = 50_000
    rates_max_bars: int = 20_000_000
    tick_probe_max_months: int = 180
    tick_probe_stop_after_empty: int = 3
    tick_full_days: int = 10
    live_probe_samples: int = 10
    closure_min_recurrence: int = 8
    reference_tz: str = "America/New_York"
    server_rule_base_offsets: tuple[int, ...] = (0, 1, 2, 3)
    confirmations: dict[str, Any] = field(default_factory=dict)
    official_costs: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


def _req(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise ConfigError(f"missing [{where}].{key}")
    return d[key]


def load_config(path: Path = DEFAULT_CONFIG) -> LensConfig:
    if not path.exists():
        raise ConfigError(f"config file not found: {path} (copy config/lens.example.toml)")
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    term = raw.get("terminal", {})
    acct = raw.get("account", {})
    sym = raw.get("symbol", {})
    ext = raw.get("extract", {})
    ana = raw.get("analysis", {})
    for forbidden_key in ("password", "investor_password", "login_password"):
        for section in raw.values():
            if isinstance(section, dict) and forbidden_key in section:
                raise ConfigError(f"credential key {forbidden_key!r} is not allowed in config")
    login = _req(acct, "expected_login", "account")
    if not isinstance(login, int) or login <= 0:
        raise ConfigError("[account].expected_login must be a positive integer")
    server = _req(acct, "expected_server", "account")
    if not isinstance(server, str) or not server.strip():
        raise ConfigError("[account].expected_server must be a non-empty string")
    tpath = _req(term, "terminal_path", "terminal")
    if not isinstance(tpath, str) or not tpath.strip():
        raise ConfigError("[terminal].terminal_path must be a non-empty string")
    forbidden = term.get("forbidden_terminal_paths", [])
    if not forbidden:
        raise ConfigError("[terminal].forbidden_terminal_paths must list the EA terminal path(s)")
    symbol = _req(sym, "name", "symbol")
    return LensConfig(
        terminal_path=tpath,
        forbidden_terminal_paths=tuple(forbidden),
        expected_login=login,
        expected_server=server,
        symbol=symbol,
        timeframes=tuple(ext.get("timeframes", ("H1", "M15", "M5", "M1"))),
        data_dir=Path(raw.get("paths", {}).get("data_dir", "data")),
        rates_chunk=int(ext.get("rates_chunk", 50_000)),
        rates_max_bars=int(ext.get("rates_max_bars", 20_000_000)),
        tick_probe_max_months=int(ext.get("tick_probe_max_months", 180)),
        tick_probe_stop_after_empty=int(ext.get("tick_probe_stop_after_empty", 3)),
        tick_full_days=int(ext.get("tick_full_days", 10)),
        live_probe_samples=int(ext.get("live_probe_samples", 10)),
        closure_min_recurrence=int(ana.get("closure_min_recurrence", 8)),
        reference_tz=str(ana.get("reference_tz", "America/New_York")),
        server_rule_base_offsets=tuple(ana.get("server_rule_base_offsets", (0, 1, 2, 3))),
        confirmations=raw.get("confirmations", {}),
        official_costs=raw.get("official_costs", {}),
        raw=raw,
    )


def load_thresholds(path: Path = DEFAULT_THRESHOLDS) -> dict[str, Any]:
    with open(path, "rb") as f:
        return tomllib.load(f)
