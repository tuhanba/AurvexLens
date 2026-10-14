"""A2 — static safety test over the source tree, with negative tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aurvex_lens.bridge import mt5_readonly
from tests._safety_scan import scan_source, scan_tree

SRC = Path(__file__).resolve().parents[1] / "src" / "aurvex_lens"


def test_source_tree_is_clean():
    assert scan_tree(SRC) == []


def test_mt5_imported_only_in_bridge():
    hits = [p.relative_to(SRC) for p in SRC.rglob("*.py") if "import MetaTrader5" in p.read_text(encoding="utf-8")]
    assert hits == [Path("bridge") / "mt5_readonly.py"]


def test_readonly_public_surface_is_exactly_whitelist():
    public = {n for n in vars(mt5_readonly.ReadOnlyMT5) if not n.startswith("_")}
    assert public - {"timeframe", "copy_ticks_all"} == set(mt5_readonly.WHITELIST)


@pytest.mark.parametrize("snippet,expect", [
    ("import MetaTrader5 as mt5\nmt5.order_send({})", "order_send"),
    ("def f(m):\n    m.order_check(r)", "order_check"),
    ("def f(m):\n    m.order_calc_margin(1, 's', 1.0, 1.0)", "order_calc_margin"),
    ("def f(m):\n    return m.positions_get()", "positions_get"),
    ("def f(m):\n    return m.orders_get()", "orders_get"),
    ("def f(m):\n    m.symbol_select('XAGUSD', True)", "symbol_select"),
    ("def f(m):\n    m.login(1, password='x', server='s')", "login"),
    ("def f(m):\n    m.initialize(path='p', login=1)", "login"),
    ("def f(m):\n    m.initialize(path='p', password='x')", "password"),
    ("def f(m):\n    m.initialize(path='p', server='s')", "server"),
    ("def f(m):\n    m.initialize('p')", "positional"),
    ("def f(m, kw):\n    m.initialize(**kw)", "**kwargs"),
    ("def f(m):\n    getattr(m, 'order_send')(r)", "order_send"),
    ("def f(m):\n    x = m.TRADE_ACTION_DEAL", "TRADE_ACTION"),
])
def test_negative_violations_are_detected(snippet, expect):
    issues = scan_source(snippet, Path("data") / "bad.py")
    assert issues, f"scanner missed: {snippet!r}"
    assert any(expect in i for i in issues)


def test_negative_mt5_import_outside_bridge():
    issues = scan_source("import MetaTrader5\n", Path("quality") / "x.py")
    assert any("outside" in i for i in issues)
    assert scan_source("import MetaTrader5\n", Path("bridge") / "mt5_readonly.py") == []


def test_negative_tree_scan(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n")
    (tmp_path / "bad.py").write_text("def f(m):\n    m.order_send({})\n")
    assert len(scan_tree(tmp_path)) == 1


def test_clean_snippet_passes():
    assert scan_source("def f(m):\n    m.initialize(path='C:/x')\n    m.copy_rates_from_pos('s', 1, 0, 10)\n",
                       Path("bridge") / "x.py") == []
