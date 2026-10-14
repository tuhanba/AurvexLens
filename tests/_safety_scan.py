"""Static safety scanner used by test_no_trade_calls.py."""

from __future__ import annotations

import ast
import re
from pathlib import Path

# Every MetaTrader5 function that sends, checks, calculates or lists orders/positions
# for trading, plus trading-related helpers. None may appear in Aurvex Lens source.
FORBIDDEN_NAMES = {
    "order_send", "order_check", "order_calc_margin", "order_calc_profit",
    "orders_get", "orders_total", "positions_get", "history_orders_get", "history_orders_total",
    "market_book_add", "market_book_get", "market_book_release", "symbol_select",
}
# Called as a function these change session state (mt5.login(...) logs in with credentials).
FORBIDDEN_CALLS = {"login"}
FORBIDDEN_PREFIX = re.compile(r"^(order_|orders_|TRADE_ACTION|ORDER_TYPE|ORDER_FILLING|ORDER_TIME)")
CREDENTIAL_KWARGS = {"login", "password", "server"}
MT5_IMPORT_ALLOWED = Path("bridge") / "mt5_readonly.py"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def scan_source(src: str, rel_path: Path) -> list[str]:
    tree = ast.parse(src)
    docs = _docstring_nodes(tree)
    issues = []

    def bad(name: str) -> bool:
        return name in FORBIDDEN_NAMES or bool(FORBIDDEN_PREFIX.match(name))

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and bad(node.attr):
            issues.append(f"{rel_path}:{node.lineno}: forbidden attribute {node.attr}")
        elif isinstance(node, ast.Name) and bad(node.id):
            issues.append(f"{rel_path}:{node.lineno}: forbidden name {node.id}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            if bad(node.value.strip()):
                issues.append(f"{rel_path}:{node.lineno}: forbidden string {node.value!r}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) else [])
            if any(n and n.split(".")[0] == "MetaTrader5" for n in names) and rel_path != MT5_IMPORT_ALLOWED:
                issues.append(f"{rel_path}:{node.lineno}: MetaTrader5 imported outside {MT5_IMPORT_ALLOWED}")
            for a in node.names:
                if bad(a.name.split(".")[-1]):
                    issues.append(f"{rel_path}:{node.lineno}: forbidden import {a.name}")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else fn.id if isinstance(fn, ast.Name) else None
            if name in FORBIDDEN_CALLS:
                issues.append(f"{rel_path}:{node.lineno}: forbidden call {name}()")
            if name == "initialize":
                if node.args:
                    issues.append(f"{rel_path}:{node.lineno}: initialize() with positional args (path= only)")
                for kw in node.keywords:
                    if kw.arg is None:
                        issues.append(f"{rel_path}:{node.lineno}: initialize(**kwargs) not allowed")
                    elif kw.arg in CREDENTIAL_KWARGS:
                        issues.append(f"{rel_path}:{node.lineno}: initialize({kw.arg}=...) credential argument")
                    elif kw.arg != "path":
                        issues.append(f"{rel_path}:{node.lineno}: initialize({kw.arg}=...) only path= allowed")
            if name in ("getattr", "__import__", "import_module") and any(
                    isinstance(a, ast.Constant) and isinstance(a.value, str) and
                    (a.value == "MetaTrader5" or bad(a.value)) for a in node.args):
                issues.append(f"{rel_path}:{node.lineno}: dynamic access to forbidden name")
    return issues


def scan_tree(root: Path) -> list[str]:
    issues = []
    for p in sorted(root.rglob("*.py")):
        issues += scan_source(p.read_text(encoding="utf-8"), p.relative_to(root))
    return issues
