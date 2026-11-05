"""Yahoo Finance adapter built on the ``yfinance`` package.

No API key is required. Yahoo is an unofficial, best-effort source: field coverage and
availability can change without notice, and Yahoo typically exposes about four annual
statements. Use ``FINANCIAL_DATA_PROVIDER=fmp`` when a contractual API is needed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pandas as pd

from src.core.interfaces import IFinancialDataProvider
from src.providers.schema import (
    FieldMap,
    FinancialDataError,
    map_record,
    pick,
    require_rows,
    statement_frame,
    weekly_closes,
)

logger = logging.getLogger(__name__)

# Yahoo row labels per canonical column, tried in order.
INCOME_MAP: FieldMap = {
    "totalRevenue": ("Total Revenue", "Operating Revenue"),
    "grossProfit": ("Gross Profit",),
    "operatingIncome": ("Operating Income", "Total Operating Income As Reported"),
    "netIncome": ("Net Income", "Net Income Common Stockholders"),
}
BALANCE_MAP: FieldMap = {
    "totalCurrentAssets": ("Current Assets", "Total Current Assets"),
    "totalCurrentLiabilities": ("Current Liabilities", "Total Current Liabilities"),
    "inventory": ("Inventory",),
    "totalAssets": ("Total Assets",),
    "totalLiabilities": (
        "Total Liabilities Net Minority Interest",
        "Total Liabilities",
    ),
    "totalShareholderEquity": (
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity",
    ),
    "shortLongTermDebtTotal": ("Total Debt",),
    "longTermDebt": ("Long Term Debt",),
    "cashAndCashEquivalentsAtCarryingValue": (
        "Cash And Cash Equivalents",
        "Cash Financial",
    ),
    "cashAndShortTermInvestments": (
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Short Term Investments",
    ),
}
CASHFLOW_MAP: FieldMap = {
    "operatingCashflow": (
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
    ),
    "capitalExpenditures": ("Capital Expenditure", "Purchase Of PPE"),
}
OVERVIEW_MAP: FieldMap = {
    "Name": ("longName", "shortName"),
    "Symbol": ("symbol",),
    "Exchange": ("fullExchangeName", "exchange"),
    "Currency": ("financialCurrency", "currency"),
    "Sector": ("sector",),
    "Industry": ("industry",),
    "MarketCapitalization": ("marketCap",),
    "SharesOutstanding": ("sharesOutstanding", "impliedSharesOutstanding"),
    "PERatio": ("trailingPE",),
    "ForwardPE": ("forwardPE",),
    "EVToEBITDA": ("enterpriseToEbitda",),
    "PriceToBookRatio": ("priceToBook",),
    "PriceToSalesRatioTTM": ("priceToSalesTrailing12Months",),
}


def statement_from_yahoo(raw: pd.DataFrame | None, field_map: FieldMap) -> pd.DataFrame:
    """Turn a Yahoo statement (line items as rows, periods as columns) into period rows."""
    if raw is None or raw.empty:
        return statement_frame([], field_map)
    records = ((str(period)[:10], raw[period].to_dict()) for period in raw.columns)
    return statement_frame(records, field_map)


def overview_from_info(info: dict[str, Any]) -> dict[str, Any]:
    return map_record(info, OVERVIEW_MAP)


def weekly_from_history(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame(columns=["date", "close"])
    frame = history.reset_index()
    frame = frame.rename(columns={frame.columns[0]: "date", "Close": "close"})
    return weekly_closes(frame[["date", "close"]])


class YFinanceProvider(IFinancialDataProvider):
    """Keyless Yahoo Finance implementation of ``IFinancialDataProvider``."""

    def __init__(
        self,
        ticker_factory: Callable[[str], Any] | None = None,
        history_period: str = "3y",
    ) -> None:
        if ticker_factory is None:
            import yfinance

            ticker_factory = yfinance.Ticker
        self._ticker_factory = ticker_factory
        self._history_period = history_period

    def _ticker(self, symbol: str) -> Any:
        return self._ticker_factory(symbol.upper().strip())

    @staticmethod
    def _fetch(label: str, symbol: str, loader: Callable[[], Any]) -> Any:
        try:
            return loader()
        except Exception as exc:  # yfinance raises varied network/parse errors
            raise FinancialDataError(
                f"Yahoo Finance {label} ({symbol}): {exc}"
            ) from exc

    # -- IFinancialDataProvider ---------------------------------------------------

    def get_income_statement(self, symbol: str, period: str) -> pd.DataFrame:
        ticker, symbol = self._ticker(symbol), symbol.upper().strip()
        quarterly = period.lower().startswith("q")
        raw = self._fetch(
            "income statement",
            symbol,
            lambda: ticker.quarterly_income_stmt if quarterly else ticker.income_stmt,
        )
        return require_rows(
            statement_from_yahoo(raw, INCOME_MAP),
            f"Yahoo Finance income statement ({symbol})",
        )

    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame:
        ticker, symbol = self._ticker(symbol), symbol.upper().strip()
        quarterly = period.lower().startswith("q")
        raw = self._fetch(
            "balance sheet",
            symbol,
            lambda: (
                ticker.quarterly_balance_sheet if quarterly else ticker.balance_sheet
            ),
        )
        return require_rows(
            statement_from_yahoo(raw, BALANCE_MAP),
            f"Yahoo Finance balance sheet ({symbol})",
        )

    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame:
        ticker, symbol = self._ticker(symbol), symbol.upper().strip()
        quarterly = period.lower().startswith("q")
        raw = self._fetch(
            "cash flow",
            symbol,
            lambda: ticker.quarterly_cashflow if quarterly else ticker.cashflow,
        )
        return require_rows(
            statement_from_yahoo(raw, CASHFLOW_MAP),
            f"Yahoo Finance cash flow ({symbol})",
        )

    def get_overview(self, symbol: str) -> dict:
        ticker, symbol = self._ticker(symbol), symbol.upper().strip()
        info = self._fetch("overview", symbol, lambda: dict(ticker.info or {}))
        record = overview_from_info(info)
        if record.get("Name") is None and record.get("MarketCapitalization") is None:
            raise FinancialDataError(
                f"Yahoo Finance overview ({symbol}): symbol not found."
            )
        record["Symbol"] = record.get("Symbol") or symbol
        return record

    def get_latest_price(self, symbol: str) -> float:
        ticker, symbol = self._ticker(symbol), symbol.upper().strip()

        def load() -> Any:
            price = pick(dict(ticker.fast_info), ("last_price", "lastPrice"))
            if price is None:
                price = pick(
                    dict(ticker.info or {}), ("currentPrice", "regularMarketPrice")
                )
            return price

        price = self._fetch("quote", symbol, load)
        if price is None:
            raise FinancialDataError(
                f"Yahoo Finance quote ({symbol}): price unavailable."
            )
        return float(price)

    def get_weekly_prices(self, symbol: str) -> pd.DataFrame:
        ticker, symbol = self._ticker(symbol), symbol.upper().strip()
        history = self._fetch(
            "prices",
            symbol,
            lambda: ticker.history(
                period=self._history_period, interval="1wk", auto_adjust=True
            ),
        )
        return require_rows(
            weekly_from_history(history), f"Yahoo Finance prices ({symbol})"
        )
