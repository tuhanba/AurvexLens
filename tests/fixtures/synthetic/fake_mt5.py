"""SYNTHETIC — NOT MARKET DATA. Fake MetaTrader5 module for tests.

Mimics the read-only subset of the MetaTrader5 Python API and records every
call so tests can assert what was (not) read. It deliberately has no
order/position-modifying functions.
"""

from __future__ import annotations

from collections import namedtuple
from datetime import datetime

from tests.fixtures.synthetic import synth

TerminalInfo = namedtuple("TerminalInfo", "community_account community_connection connected dlls_allowed "
                          "trade_allowed tradeapi_disabled email_enabled ftp_enabled notifications_enabled mqid "
                          "build maxbars codepage ping_last community_balance retransmission company name "
                          "language path data_path commondata_path")
AccountInfo = namedtuple("AccountInfo", "login trade_mode leverage limit_orders margin_so_mode trade_allowed "
                         "trade_expert margin_mode currency_digits fifo_close balance credit profit equity margin "
                         "margin_free margin_level margin_so_call margin_so_so margin_initial margin_maintenance "
                         "assets liabilities commission_blocked name server currency company")
Tick = namedtuple("Tick", "time bid ask last volume time_msc flags volume_real")
SymbolInfo = namedtuple("SymbolInfo", "name digits point spread trade_contract_size trade_tick_size "
                        "trade_tick_value volume_min volume_step volume_max swap_mode swap_long swap_short "
                        "swap_rollover3days currency_base currency_profit path visible")
Sym = namedtuple("Sym", "name")
TradeDeal = namedtuple("TradeDeal", "ticket order time time_msc type entry magic position_id reason volume price "
                       "commission swap profit fee symbol comment external_id")

TERMINAL_PATH = r"C:\AurvexLens\mt5"
LOGIN = 12345678
SERVER = "SYNTH-Server"


class FakeMT5:
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_H1 = 1, 5, 15, 16385
    COPY_TICKS_ALL = -1
    _TF = {1: 1, 5: 5, 15: 15, 16385: 60}

    def __init__(self, *, init_ok=True, path=TERMINAL_PATH, login=LOGIN, server=SERVER,
                 account_trade_allowed=False, terminal_trade_allowed=False, drop_fields=(),
                 maxbars=100_000_000, symbol="XAGUSD", symbol_visible=True, deals_mode="normal"):
        self.calls: list[str] = []
        self.init_kwargs: dict | None = None
        self.init_ok = init_ok
        self.path = path
        self.login = login
        self.server = server
        self.account_trade_allowed = account_trade_allowed
        self.terminal_trade_allowed = terminal_trade_allowed
        self.drop_fields = set(drop_fields)
        self.maxbars = maxbars
        self.symbol = symbol
        self.symbol_visible = symbol_visible
        self.deals_mode = deals_mode  # normal | fee | nofee | zero | positive | none | denied
        self.live_clock = None  # set to a FakeClock to get ticks that advance with the system clock
        self.live_offset_s = 0

    def _rec(self, name):
        self.calls.append(name)

    def initialize(self, *args, **kwargs):
        self._rec("initialize")
        self.init_kwargs = dict(kwargs, _args=args)
        return self.init_ok

    def shutdown(self):
        self._rec("shutdown")

    def last_error(self):
        self._rec("last_error")
        return (1, "Success") if self.init_ok else (-10003, "IPC initialize failed")

    def version(self):
        self._rec("version")
        return (500, 5000, "01 Jan 2026")

    def terminal_info(self):
        self._rec("terminal_info")
        ti = TerminalInfo(False, False, True, False, self.terminal_trade_allowed, False, False, False, False, 0,
                          5000, self.maxbars, 1252, 10.0, 0.0, 0.0, synth.SYNTHETIC_LABEL,
                          "SYNTHETIC TERMINAL", "English", self.path, r"C:\synthetic\data", r"C:\synthetic\common")
        return _drop(ti, self.drop_fields)

    def account_info(self):
        self._rec("account_info")
        ai = AccountInfo(self.login, 0, 100, 0, 0, self.account_trade_allowed, False, 2, 2, False, 100000.0,
                         0.0, 0.0, 100000.0, 0.0, 100000.0, 0.0, 50.0, 30.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                         "SYNTHETIC NAME", self.server, "USD", synth.SYNTHETIC_LABEL)
        return _drop(ai, self.drop_fields)

    def symbol_info(self, symbol):
        self._rec("symbol_info")
        if symbol != self.symbol:
            return None
        return SymbolInfo(symbol, 3, synth.POINT, 20, 5000.0, 0.001, 5.0, 0.01, 0.01, 100.0, 1, -10.0, 2.0, 3,
                          "XAG", "USD", "Metals\\" + symbol, self.symbol_visible)

    def symbols_get(self, group=None):
        self._rec("symbols_get")
        return (Sym(self.symbol), Sym("XAGEUR"))

    def symbol_info_tick(self, symbol):
        self._rec("symbol_info_tick")
        r = synth.ticks().iloc[-1]
        if self.live_clock is not None:  # fresh tick ~0.2 s old at server offset live_offset_s
            msc = int((self.live_clock.time() + self.live_offset_s - 0.2) * 1000)
            return Tick(msc // 1000, float(r.bid), float(r.ask), 0.0, 0, msc, 6, 0.0)
        return Tick(int(r.time), float(r.bid), float(r.ask), 0.0, 0, int(r.time_msc), 6, 0.0)

    def copy_rates_from_pos(self, symbol, timeframe, start_pos, count):
        self._rec("copy_rates_from_pos")
        arr = synth.to_rates_array(synth.bars(self._TF[timeframe]))
        end = len(arr) - start_pos
        if end <= 0:
            return None
        return arr[max(0, end - count):end]

    def copy_rates_range(self, symbol, timeframe, date_from, date_to):
        self._rec("copy_rates_range")
        arr = synth.to_rates_array(synth.bars(self._TF[timeframe]))
        a, b = _ts(date_from), _ts(date_to)
        return arr[(arr["time"] >= a) & (arr["time"] <= b)]

    def copy_ticks_range(self, symbol, date_from, date_to, flags):
        self._rec("copy_ticks_range")
        arr = synth.to_ticks_array(synth.ticks())
        a, b = _ts(date_from) * 1000, _ts(date_to) * 1000
        return arr[(arr["time_msc"] >= a) & (arr["time_msc"] <= b)]

    def copy_ticks_from(self, symbol, date_from, count, flags):
        self._rec("copy_ticks_from")
        arr = synth.to_ticks_array(synth.ticks())
        return arr[arr["time_msc"] >= _ts(date_from) * 1000][:count]

    def history_deals_total(self, date_from, date_to):
        self._rec("history_deals_total")
        return 0 if self.deals_mode in ("none", "denied") else len(synthetic_deals(self.symbol, self.deals_mode))

    def history_deals_get(self, date_from, date_to):
        self._rec("history_deals_get")
        if self.deals_mode == "denied":
            return None
        if self.deals_mode == "none":
            return ()
        return synthetic_deals(self.symbol, self.deals_mode)

    def positions_total(self):
        self._rec("positions_total")
        return 0


def _ts(d) -> int:
    return int(d.timestamp()) if isinstance(d, datetime) else int(d)


def _drop(nt, fields):
    """Simulate a field that does not exist in this terminal build."""
    if not fields:
        return nt
    keep = [f for f in nt._fields if f not in fields]
    T = namedtuple(type(nt).__name__, keep)
    return T(*(getattr(nt, f) for f in keep))


# Distinctive per-deal values: tests assert none of them ever reach disk, reports or stdout.
DEAL_TICKET_BASE = 9_100_000
DEAL_POSITION_BASE = 7_700_000
DEAL_PRICE = 31.41593
DEAL_PROFIT = 271.828
DEAL_TIME = 1_773_000_123
BALANCE_AMOUNT = 123_456.78
TradeDealNoFee = namedtuple("TradeDeal", "ticket order time time_msc type entry magic position_id reason volume "
                            "price commission swap profit symbol comment external_id")


def synthetic_deals(symbol: str, mode: str = "normal") -> tuple:
    """SYNTHETIC — NOT MARKET DATA.

    Commission -2.5 per lot per side (round turn -5.0); fee 0 (mode "fee": -0.5/lot/side).
    Positions 0..2 fully closed (pos 2 closed in two parts), pos 3 open, pos 5 contains an INOUT
    deal (excluded from round turn). Plus a non-trade deal type on the symbol, an other-symbol deal
    and two symbol-less deals (balance type 2, commission type 7).
    Modes: normal | fee | nofee | zero | positive.
    """
    comm = {"zero": 0.0, "positive": 2.5}.get(mode, -2.5)
    fee = {"fee": -0.5}.get(mode, 0.0)
    rows = []
    t = DEAL_TICKET_BASE

    def deal(pos, entry, vol, sym=symbol, typ=0, c=None, profit=None):
        nonlocal t
        t += 1
        c = comm if c is None else c
        pr = profit if profit is not None else (DEAL_PROFIT if entry == 1 else 0.0)
        common = (t, t, DEAL_TIME + t % 1000, (DEAL_TIME + t % 1000) * 1000, typ, entry, 0,
                  DEAL_POSITION_BASE + pos, 0, vol, DEAL_PRICE, c * vol, 0.0, pr)
        if mode == "nofee":
            rows.append(TradeDealNoFee(*common, sym, "", ""))
        else:
            rows.append(TradeDeal(*common, fee * vol, sym, "", ""))

    deal(0, 0, 1.0); deal(0, 1, 1.0, typ=1)
    deal(1, 0, 0.5, typ=1); deal(1, 1, 0.5)
    deal(2, 0, 2.0); deal(2, 1, 1.0, typ=1); deal(2, 1, 1.0, typ=1)
    deal(3, 0, 0.3)
    deal(5, 0, 1.0); deal(5, 2, 2.0, typ=1); deal(5, 1, 1.0)
    deal(6, 0, 0.0, typ=6, c=0.0)                       # non-trade deal type on the symbol
    deal(4, 0, 1.0, sym="EURUSD", c=-9.0)
    deal(0, 0, 0.0, sym="", typ=2, c=0.0, profit=BALANCE_AMOUNT)   # balance
    deal(0, 0, 0.0, sym="", typ=7, c=0.0, profit=-12.34)           # commission booked separately
    return tuple(rows)


class FakeClock:
    """Deterministic system clock for the live probe: sleep() advances time()."""

    def __init__(self, start: float):
        self.t = float(start)

    def time(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s
