from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

import pandas as pd

from src.core.cache import ICacheProvider
from src.core.interfaces import IFinancialDataProvider

T = TypeVar("T")


class CachedFinancialProvider(IFinancialDataProvider):
    """Decorator that keeps vendor responses in the shared TTL cache.

    Vendors rate-limit requests, and the DCF, ratio, snapshot, and chat tools all
    read the same statements. Caching at the provider keeps every consumer inside
    that budget.
    """

    def __init__(
        self,
        inner: IFinancialDataProvider,
        cache: ICacheProvider,
        ttl: int,
        namespace: str = "fin",
    ) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl
        self._namespace = namespace

    def _cached(self, key: str, loader: Callable[[], T]) -> T:
        hit = self._cache.get(key)
        if hit is not None:
            return hit.copy() if isinstance(hit, pd.DataFrame) else hit
        value = loader()
        self._cache.set(key, value, ttl=self._ttl)
        return value.copy() if isinstance(value, pd.DataFrame) else value

    def _key(self, kind: str, symbol: str, extra: str = "") -> str:
        # The namespace is the active vendor, so switching sources never serves
        # another vendor's cached payload.
        return f"{self._namespace}:{kind}:{symbol.upper().strip()}:{extra}"

    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame:
        return self._cached(
            self._key("balance", symbol, period.lower()),
            lambda: self._inner.get_balance_sheet(symbol, period),
        )

    def get_income_statement(self, symbol: str, period: str) -> pd.DataFrame:
        return self._cached(
            self._key("income", symbol, period.lower()),
            lambda: self._inner.get_income_statement(symbol, period),
        )

    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame:
        return self._cached(
            self._key("cashflow", symbol, period.lower()),
            lambda: self._inner.get_cash_flow(symbol, period),
        )

    def get_overview(self, symbol: str) -> dict:
        return self._cached(
            self._key("overview", symbol), lambda: self._inner.get_overview(symbol)
        )

    def get_latest_price(self, symbol: str) -> float:
        return self._cached(
            self._key("quote", symbol), lambda: self._inner.get_latest_price(symbol)
        )

    def get_weekly_prices(self, symbol: str) -> pd.DataFrame:
        return self._cached(
            self._key("weekly", symbol), lambda: self._inner.get_weekly_prices(symbol)
        )
