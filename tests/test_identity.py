"""A3 — identity checks with a fake MT5 (SYNTHETIC — NOT MARKET DATA)."""

from __future__ import annotations

import json

import pytest

from aurvex_lens.bridge.identity import (
    EXIT_FAIL, EXIT_INIT, EXIT_OK, EXIT_UNKNOWN, FAIL, PASS, UNKNOWN, WARN, verify_identity,
)
from aurvex_lens.bridge.mt5_readonly import ReadOnlyMT5
from aurvex_lens.cli import cmd_extract, cmd_identity
from aurvex_lens.common.config import ConfigError, load_config
from tests.conftest import write_config
from tests.fixtures.synthetic.fake_mt5 import FakeMT5

IDENTITY_CALLS = {"initialize", "version", "terminal_info", "account_info", "last_error", "shutdown"}


def _result(rep, cid):
    return next(c.result for c in rep.checks if c.id == cid)


def test_all_pass(make_cfg, fake):
    rep = verify_identity(ReadOnlyMT5(fake), make_cfg())
    assert rep.overall == PASS and rep.exit_code == EXIT_OK
    assert fake.init_kwargs == {"path": r"C:\AurvexLens\mt5\terminal64.exe", "_args": ()}


@pytest.mark.parametrize("label,fake_kw,cfg_kw,cid,expected_exit", [
    ("wrong_path", {"path": r"C:\Other\MT5"}, {}, "I1_terminal_path", EXIT_FAIL),
    ("forbidden_path", {}, {"forbidden": [r"C:\AurvexLens\mt5\terminal64.exe"]}, "I2_not_forbidden", EXIT_FAIL),
    ("other_login", {"login": 87654321}, {}, "I3_login", EXIT_FAIL),
    ("other_server", {"server": "Other-Server"}, {}, "I4_server", EXIT_FAIL),
    ("trade_allowed", {"account_trade_allowed": True}, {}, "I5_account_trade_allowed", EXIT_FAIL),
])
def test_failures_exit_nonzero_and_read_no_data(tmp_path, label, fake_kw, cfg_kw, cid, expected_exit):
    fake = FakeMT5(**fake_kw)
    cfg = load_config(write_config(tmp_path, **cfg_kw))
    rc = cmd_extract(cfg, backend=fake, data_origin="SYNTHETIC", sleep=lambda s: None)
    assert rc == expected_exit != 0
    assert set(fake.calls) <= IDENTITY_CALLS, f"{label}: read beyond identity: {fake.calls}"
    assert not (cfg.data_dir / "raw").exists()
    rep = verify_identity(ReadOnlyMT5(FakeMT5(**fake_kw)), cfg)
    assert _result(rep, cid) == FAIL


def test_forbidden_path_never_initializes(make_cfg):
    fake = FakeMT5()
    cfg = make_cfg(forbidden=[r"c:/aurvexlens/MT5/"])  # same folder, different spelling
    rep = verify_identity(ReadOnlyMT5(fake), cfg)
    assert rep.exit_code == EXIT_FAIL
    assert fake.calls == []


def test_observed_path_in_forbidden_list(make_cfg):
    fake = FakeMT5(path=r"C:\Program Files\EA Terminal")
    rep = verify_identity(ReadOnlyMT5(fake), make_cfg())
    assert rep.exit_code == EXIT_FAIL
    assert _result(rep, "I2_observed_not_forbidden") == FAIL


def test_terminal_algo_trading_is_warning_only(make_cfg):
    rep = verify_identity(ReadOnlyMT5(FakeMT5(terminal_trade_allowed=True)), make_cfg())
    assert _result(rep, "I6_terminal_trade_allowed") == WARN
    assert rep.exit_code == EXIT_OK


@pytest.mark.parametrize("field", ["trade_allowed", "login", "server", "path"])
def test_missing_field_is_unknown(make_cfg, field):
    rep = verify_identity(ReadOnlyMT5(FakeMT5(drop_fields={field})), make_cfg())
    assert UNKNOWN in {c.result for c in rep.checks}
    assert rep.exit_code == EXIT_UNKNOWN


def test_init_failure(make_cfg):
    fake = FakeMT5(init_ok=False)
    rep = verify_identity(ReadOnlyMT5(fake), make_cfg())
    assert rep.exit_code == EXIT_INIT and not rep.initialized
    assert "terminal_info" not in fake.calls


def test_identity_report_json_masked(make_cfg, capsys):
    cfg = make_cfg()
    fake = FakeMT5()
    assert cmd_identity(cfg, backend=fake) == EXIT_OK
    assert fake.calls[-1] == "shutdown"
    files = list((cfg.data_dir / "reports" / "identity").rglob("identity_report.json"))
    assert len(files) == 1
    text = files[0].read_text(encoding="utf-8")
    assert "12345678" not in text and "****5678" in text
    assert "12345678" not in capsys.readouterr().out
    doc = json.loads(text)
    for c in doc["checks"]:
        assert {"observed", "expected", "result"} <= set(c)
    assert "balance" not in text and "SYNTHETIC NAME" not in text


def test_config_rejects_password(tmp_path):
    p = write_config(tmp_path)
    p.write_text(p.read_text().replace("[account]", "[account]\npassword = 'x'"))
    with pytest.raises(ConfigError):
        load_config(p)


@pytest.mark.parametrize("cfg_path,observed", [
    (r"C:\AurvexLens\mt5\terminal64.exe", r"C:\AurvexLens\mt5"),
    (r"C:/AurvexLens/mt5/terminal64.exe", r"C:\AurvexLens\mt5"),        # forward vs back slash
    (r"C:\AurvexLens\mt5\terminal64.exe", "C:\\AurvexLens\\mt5\\"),  # trailing separator
    (r"c:\aurvexlens\MT5\TERMINAL64.EXE", r"C:\AurvexLens\mt5"),        # case
    (r"C:\AurvexLens\.\mt5\terminal64.exe", r"C:/AurvexLens/mt5/"),
])
def test_path_normalization_d_i1(make_cfg, cfg_path, observed):
    rep = verify_identity(ReadOnlyMT5(FakeMT5(path=observed)), make_cfg(terminal_path=cfg_path))
    assert _result(rep, "I1_terminal_path") == PASS


@pytest.mark.parametrize("forbidden", [
    r"C:/AurvexLens/mt5/terminal64.exe", "c:\\AURVEXLENS\\mt5\\", r"C:\AurvexLens\mt5",
])
def test_forbidden_path_same_normalization(make_cfg, forbidden):
    fake = FakeMT5()
    rep = verify_identity(ReadOnlyMT5(fake), make_cfg(forbidden=[forbidden]))
    assert rep.exit_code == EXIT_FAIL and fake.calls == []


def test_normalization_function():
    from aurvex_lens.common.config import normalize_win_path, terminal_dir
    assert normalize_win_path("C:/A/B/") == normalize_win_path(r"c:\a\b") == r"c:\a\b"
    assert terminal_dir(r"C:\X\Y\terminal64.exe") == r"c:\x\y"
