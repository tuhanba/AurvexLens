"""Identity verification before any data is read (spec §3 item 3).

Rules:
- The configured terminal path must not be in `forbidden_terminal_paths`;
  this is checked BEFORE initialize() so the EA terminal is never attached.
- initialize() is called with path= only.
- Only version / terminal_info / account_info / last_error are read here.
- Any field that is missing, None or of unexpected type yields UNKNOWN; the
  process must stop and ask the user (never assume).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aurvex_lens.bridge.mt5_readonly import ReadOnlyMT5, backend_package_version
from aurvex_lens.common.config import LensConfig, normalize_win_path, terminal_dir
from aurvex_lens.common.masking import mask_login
from aurvex_lens.common.provenance import to_jsonable, utc_iso

PASS, FAIL, UNKNOWN, WARN = "PASS", "FAIL", "UNKNOWN", "WARN"

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_UNKNOWN = 3
EXIT_CONFIG = 4
EXIT_INIT = 5

# Account / terminal fields recorded for P0.3 (investor-session behaviour).
# Balance, equity, name and data paths are deliberately excluded.
_ACCOUNT_FIELDS = (
    "trade_allowed", "trade_expert", "trade_mode", "margin_mode",
    "limit_orders", "currency", "company",
)
_TERMINAL_FIELDS = (
    "build", "connected", "trade_allowed", "tradeapi_disabled", "dlls_allowed",
    "maxbars", "name", "company", "path",
)


@dataclass
class Check:
    id: str
    field: str
    observed: Any
    expected: Any
    result: str
    note: str = ""


@dataclass
class IdentityReport:
    checks: list[Check] = field(default_factory=list)
    observed_account: dict[str, Any] = field(default_factory=dict)
    observed_terminal: dict[str, Any] = field(default_factory=dict)
    terminal_version: Any = None
    package_version: str = ""
    initialized: bool = False
    init_error: Any = None
    checked_at_utc: str = field(default_factory=utc_iso)

    @property
    def overall(self) -> str:
        results = {c.result for c in self.checks}
        if not self.initialized and FAIL not in results:
            return FAIL
        if FAIL in results:
            return FAIL
        if UNKNOWN in results:
            return UNKNOWN
        return PASS

    @property
    def exit_code(self) -> int:
        if not self.initialized and not any(c.result == FAIL for c in self.checks):
            return EXIT_INIT
        return {PASS: EXIT_OK, FAIL: EXIT_FAIL, UNKNOWN: EXIT_UNKNOWN}[self.overall]

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": "identity_report",
            "checked_at_utc": self.checked_at_utc,
            "overall": self.overall,
            "exit_code": self.exit_code,
            "initialized": self.initialized,
            "init_error": to_jsonable(self.init_error),
            "terminal_version": to_jsonable(self.terminal_version),
            "metatrader5_package_version": self.package_version,
            "checks": [to_jsonable(c.__dict__) for c in self.checks],
            "observed_account_fields": self.observed_account,
            "observed_terminal_fields": self.observed_terminal,
            "note": "Account number is masked. Balance/equity/name are not read into this report.",
        }


def _get(obj: Any, name: str) -> tuple[bool, Any]:
    if obj is None or not hasattr(obj, name):
        return False, None
    return True, getattr(obj, name)


def _forbidden_set(cfg: LensConfig) -> set[str]:
    out: set[str] = set()
    for p in cfg.forbidden_terminal_paths:
        out.add(normalize_win_path(p))
        out.add(terminal_dir(p))
    return out


def precheck_paths(cfg: LensConfig) -> Check:
    """Configured path vs forbidden list — runs before any MT5 call."""
    forb = _forbidden_set(cfg)
    hit = normalize_win_path(cfg.terminal_path) in forb or terminal_dir(cfg.terminal_path) in forb
    return Check(
        id="I2_not_forbidden",
        field="config.terminal_path",
        observed=cfg.terminal_path,
        expected="not in forbidden_terminal_paths",
        result=FAIL if hit else PASS,
        note="checked before initialize(); EA terminal is never attached" if hit else "",
    )


def verify_identity(mt5: ReadOnlyMT5, cfg: LensConfig) -> IdentityReport:
    """Initialize (path= only) and run identity checks. Caller must shutdown()
    if report.initialized is True. Reads nothing beyond identity fields."""
    rep = IdentityReport(package_version=backend_package_version())
    pre = precheck_paths(cfg)
    rep.checks.append(pre)
    if pre.result != PASS:
        return rep

    ok = mt5.initialize(path=cfg.terminal_path)
    if not ok:
        rep.init_error = mt5.last_error()
        return rep
    rep.initialized = True
    rep.terminal_version = mt5.version()
    ti = mt5.terminal_info()
    ai = mt5.account_info()

    for name in _TERMINAL_FIELDS:
        present, val = _get(ti, name)
        rep.observed_terminal[name] = to_jsonable(val) if present else "FIELD_ABSENT"
    for name in _ACCOUNT_FIELDS:
        present, val = _get(ai, name)
        rep.observed_account[name] = to_jsonable(val) if present else "FIELD_ABSENT"
    present, login_val = _get(ai, "login")
    rep.observed_account["login_masked"] = mask_login(login_val) if present else "FIELD_ABSENT"
    present, server_val = _get(ai, "server")
    rep.observed_account["server"] = server_val if present else "FIELD_ABSENT"

    # I1 — terminal path
    present, path_val = _get(ti, "path")
    if not present or not isinstance(path_val, str) or not path_val:
        rep.checks.append(Check("I1_terminal_path", "terminal_info().path", path_val,
                                terminal_dir(cfg.terminal_path), UNKNOWN, "field absent or not a string"))
    else:
        obs = normalize_win_path(path_val)
        exp = terminal_dir(cfg.terminal_path)
        rep.checks.append(Check("I1_terminal_path", "terminal_info().path", path_val, exp,
                                PASS if obs == exp else FAIL,
                                "compared case-insensitively against the folder of terminal_path"))
        if obs in _forbidden_set(cfg):
            rep.checks.append(Check("I2_observed_not_forbidden", "terminal_info().path", path_val,
                                    "not in forbidden_terminal_paths", FAIL,
                                    "connected terminal is a forbidden (EA) terminal"))

    # I3 — login
    if not present_int(ai, "login"):
        rep.checks.append(Check("I3_login", "account_info().login", "FIELD_ABSENT_OR_INVALID",
                                mask_login(cfg.expected_login), UNKNOWN))
    else:
        rep.checks.append(Check("I3_login", "account_info().login", mask_login(login_val),
                                mask_login(cfg.expected_login),
                                PASS if int(login_val) == cfg.expected_login else FAIL))

    # I4 — server
    present_s, server_val = _get(ai, "server")
    if not present_s or not isinstance(server_val, str) or not server_val:
        rep.checks.append(Check("I4_server", "account_info().server", server_val,
                                cfg.expected_server, UNKNOWN))
    else:
        rep.checks.append(Check("I4_server", "account_info().server", server_val, cfg.expected_server,
                                PASS if server_val == cfg.expected_server else FAIL))

    # I5 — account trade_allowed must be False (investor session expectation)
    present_t, ta = _get(ai, "trade_allowed")
    if not present_t or not isinstance(ta, bool):
        rep.checks.append(Check("I5_account_trade_allowed", "account_info().trade_allowed", ta, False,
                                UNKNOWN, "field absent or not bool; investor behaviour unverified"))
    else:
        rep.checks.append(Check("I5_account_trade_allowed", "account_info().trade_allowed", ta, False,
                                PASS if ta is False else FAIL,
                                "" if ta is False else "trading allowed → not an investor session"))

    # I6 — terminal Algo Trading button: False expected, True is a warning
    present_tt, tta = _get(ti, "trade_allowed")
    if not present_tt or not isinstance(tta, bool):
        rep.checks.append(Check("I6_terminal_trade_allowed", "terminal_info().trade_allowed", tta, False,
                                UNKNOWN, "field absent or not bool"))
    else:
        rep.checks.append(Check("I6_terminal_trade_allowed", "terminal_info().trade_allowed", tta, False,
                                PASS if tta is False else WARN,
                                "" if tta is False else "Algo Trading enabled in this terminal (warning only)"))
    return rep


def present_int(obj: Any, name: str) -> bool:
    present, val = _get(obj, name)
    return present and isinstance(val, int) and not isinstance(val, bool) and val > 0
