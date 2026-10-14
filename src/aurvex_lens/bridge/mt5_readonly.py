"""The ONLY module allowed to import the MetaTrader5 package.

Exposes a fixed whitelist of read-only functions. Nothing else from the
MetaTrader5 module is reachable through this wrapper. `initialize` is only
ever called with `path=`; credentials are never passed (the user logs in
manually with the investor password in a separate terminal).
"""

from __future__ import annotations

from typing import Any

# Read-only functions exposed by ReadOnlyMT5 (spec §10 step 3). Kept as data so
# tests can assert the public surface equals this list exactly.
WHITELIST: tuple[str, ...] = (
    "initialize",
    "shutdown",
    "version",
    "terminal_info",
    "account_info",
    "symbol_info",
    "symbol_info_tick",
    "symbols_get",
    "copy_rates_from_pos",
    "copy_rates_range",
    "copy_ticks_range",
    "copy_ticks_from",
    "history_deals_total",
    "history_deals_get",
    "positions_total",
    "last_error",
)

_TIMEFRAMES = ("M1", "M5", "M15", "H1")


def _load_backend() -> Any:
    import MetaTrader5  # noqa: PLC0415 — the single permitted import site

    return MetaTrader5


def backend_package_version() -> str:
    """Installed MetaTrader5 package version, or 'NOT_INSTALLED'."""
    try:
        from importlib.metadata import version

        return version("MetaTrader5")
    except Exception:  # noqa: BLE001
        return "NOT_INSTALLED"


class ReadOnlyMT5:
    """Whitelisted read-only facade over the MetaTrader5 module.

    `backend` is injectable for tests (a fake module object). In production it
    is the real MetaTrader5 module.
    """

    __slots__ = ("__backend",)

    def __init__(self, backend: Any | None = None) -> None:
        self.__backend = backend if backend is not None else _load_backend()

    # -- constants -------------------------------------------------------
    def timeframe(self, name: str) -> int:
        if name not in _TIMEFRAMES:
            raise ValueError(f"unsupported timeframe {name!r}")
        return getattr(self.__backend, "TIMEFRAME_" + name)

    @property
    def copy_ticks_all(self) -> int:
        return self.__backend.COPY_TICKS_ALL

    # -- whitelist -------------------------------------------------------
    def initialize(self, path: str) -> bool:
        return self.__backend.initialize(path=path)

    def shutdown(self) -> None:
        return self.__backend.shutdown()

    def version(self) -> Any:
        return self.__backend.version()

    def terminal_info(self) -> Any:
        return self.__backend.terminal_info()

    def account_info(self) -> Any:
        return self.__backend.account_info()

    def symbol_info(self, symbol: str) -> Any:
        return self.__backend.symbol_info(symbol)

    def symbol_info_tick(self, symbol: str) -> Any:
        return self.__backend.symbol_info_tick(symbol)

    def symbols_get(self, group: str) -> Any:
        return self.__backend.symbols_get(group=group)

    def copy_rates_from_pos(self, symbol: str, timeframe: int, start_pos: int, count: int) -> Any:
        return self.__backend.copy_rates_from_pos(symbol, timeframe, start_pos, count)

    def copy_rates_range(self, symbol: str, timeframe: int, date_from: Any, date_to: Any) -> Any:
        return self.__backend.copy_rates_range(symbol, timeframe, date_from, date_to)

    def copy_ticks_range(self, symbol: str, date_from: Any, date_to: Any, flags: int) -> Any:
        return self.__backend.copy_ticks_range(symbol, date_from, date_to, flags)

    def copy_ticks_from(self, symbol: str, date_from: Any, count: int, flags: int) -> Any:
        return self.__backend.copy_ticks_from(symbol, date_from, count, flags)

    def history_deals_total(self, date_from: Any, date_to: Any) -> Any:
        return self.__backend.history_deals_total(date_from, date_to)

    def history_deals_get(self, date_from: Any, date_to: Any) -> Any:
        return self.__backend.history_deals_get(date_from, date_to)

    def positions_total(self) -> Any:
        return self.__backend.positions_total()

    def last_error(self) -> Any:
        return self.__backend.last_error()
