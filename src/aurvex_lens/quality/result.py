"""Criterion result container. No aggregate quality score exists by design."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
NOT_APPLICABLE_MARKET_CLOSED = "NOT_APPLICABLE_MARKET_CLOSED"
NOT_CONNECTED = "NOT_CONNECTED"  # C7: no calendar source (decision D-C7); never PASS
RESULTS = (PASS, FAIL, UNKNOWN, NOT_APPLICABLE_MARKET_CLOSED, NOT_CONNECTED)
UNAPPROVED_TZ_LABEL = "UYARI: saat dilimi kuralı onaylanmadı — time_utc değerleri ONAYSIZ"


def is_pass(result: str) -> bool:
    """Only PASS passes. UNKNOWN, NOT_CONNECTED, NOT_APPLICABLE_* never do."""
    return result == PASS


def data_gate(criteria: list["CriterionResult"]) -> dict:
    """Phase-1 data gate: every blocking criterion must be PASS (spec §2.3 DATA_INSUFFICIENT)."""
    failing = [{"id": c.id, "result": c.result} for c in criteria if c.blocking and not is_pass(c.result)]
    return {"status": "DATA_INSUFFICIENT" if failing else "DATA_SUFFICIENT", "not_passing": failing}


def combine(results: list[str]) -> str:
    """FAIL dominates, then UNKNOWN; UNKNOWN is never PASS. Empty -> UNKNOWN."""
    if not results:
        return UNKNOWN
    if FAIL in results:
        return FAIL
    if any(r != PASS for r in results):
        return UNKNOWN
    return PASS


@dataclass
class CriterionResult:
    id: str
    title: str
    result: str
    method: str
    metrics: dict[str, Any] = field(default_factory=dict)
    sub_results: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tables: list[dict[str, Any]] = field(default_factory=list)  # {"title", "columns", "rows", "utc": bool}
    blocking: bool = True
