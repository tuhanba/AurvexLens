"""Masking of account identifiers in logs and reports (spec §3.7)."""

from __future__ import annotations


def mask_login(login: object) -> str:
    """`12345678` -> `****5678`. Unknown/empty values -> `****`."""
    if login is None:
        return "****"
    s = str(login).strip()
    if not s:
        return "****"
    return "****" + s[-4:] if len(s) > 4 else "****"
