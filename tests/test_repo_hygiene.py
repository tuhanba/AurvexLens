"""A9 — local config and data are never committed."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _ignored(path: str) -> bool:
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO, check=False)
    return r.returncode == 0


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
@pytest.mark.parametrize("path", ["config/local.toml", "data/raw/x/meta.json", "data/reports/x/report.md", "run.log"])
def test_ignored(path):
    assert _ignored(path)


@pytest.mark.skipif(not (REPO / ".git").exists(), reason="not a git checkout")
def test_not_tracked():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()
    assert "config/local.toml" not in out
    assert not [p for p in out if p.startswith("data/")]


def test_thresholds_marked_proposed():
    text = (REPO / "config" / "quality_thresholds.toml").read_text(encoding="utf-8")
    assert "PROPOSED — user approval pending" in text


def test_readme_commands_not_chained():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert "&&" not in text and " ; " not in text
