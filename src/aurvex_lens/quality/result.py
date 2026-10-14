"""Criterion result container. No aggregate quality score exists by design."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"
NOT_APPLICABLE_MARKET_CLOSED = "NOT_APPLICABLE_MARKET_CLOSED"
UNAPPROVED_TZ_LABEL = "UYARI: saat dilimi kuralı onaylanmadı — time_utc değerleri ONAYSIZ"


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
