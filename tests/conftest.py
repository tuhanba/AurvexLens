"""Shared fixtures. All data here is SYNTHETIC — NOT MARKET DATA."""

from __future__ import annotations

from pathlib import Path

import pytest

from aurvex_lens.common.config import load_config
from tests.fixtures.synthetic.fake_mt5 import FakeMT5, LOGIN, SERVER

REPO = Path(__file__).resolve().parents[1]
THRESHOLDS = REPO / "config" / "quality_thresholds.toml"


def write_config(tmp_path: Path, **over) -> Path:
    vals = {
        "terminal_path": r"C:\AurvexLens\mt5\terminal64.exe",
        "forbidden": [r"C:\Program Files\EA Terminal\terminal64.exe"],
        "login": LOGIN, "server": SERVER, "symbol": "XAGUSD", "confirmations": "",
    }
    vals.update(over)
    forb = ", ".join(f"'{p}'" for p in vals["forbidden"])
    text = f"""
[terminal]
terminal_path = '{vals["terminal_path"]}'
forbidden_terminal_paths = [{forb}]
[account]
expected_login = {vals["login"]}
expected_server = "{vals["server"]}"
[symbol]
name = "{vals["symbol"]}"
[paths]
data_dir = '{(tmp_path / "data").as_posix()}'
[extract]
tick_probe_max_months = 12
tick_full_days = 10
live_probe_samples = 2
rates_chunk = 20000
[analysis]
closure_min_recurrence = 4
reference_tz = "America/New_York"
[confirmations]
{vals["confirmations"]}
"""
    p = tmp_path / "local.toml"
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def make_cfg(tmp_path):
    def _make(**over):
        return load_config(write_config(tmp_path, **over))
    return _make


@pytest.fixture
def fake():
    return FakeMT5()
