from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class IFinancialDataProvider(ABC):
    @abstractmethod
    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_income_statement(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_overview(self, symbol: str) -> dict: ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float: ...


class INewsDataProvider(ABC):
    @abstractmethod
    def search_news(self, query: str, days: int, max_results: int) -> dict: ...

    @abstractmethod
    def fetch_desk_brief(self, topic: str) -> str: ...


class IFundamentalProvider(ABC):
    @abstractmethod
    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_income_statement(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_overview(self, symbol: str) -> dict: ...


class IValuationProvider(ABC):
    @abstractmethod
    def get_overview(self, symbol: str) -> dict: ...

    @abstractmethod
    def get_latest_price(self, symbol: str) -> float: ...

    @abstractmethod
    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame: ...

    @abstractmethod
    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame: ...


class INewsProvider(ABC):
    @abstractmethod
    def search_news(self, query: str, days: int, max_results: int) -> dict: ...

    @abstractmethod
    def fetch_desk_brief(self, topic: str) -> str: ...
