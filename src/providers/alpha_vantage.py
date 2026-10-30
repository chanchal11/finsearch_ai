from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from alpha_vantage.fundamentaldata import FundamentalData
from alpha_vantage.timeseries import TimeSeries

from src.core.interfaces import IFinancialDataProvider

logger = logging.getLogger(__name__)


class AlphaVantageError(RuntimeError):
    pass


class AlphaVantageProvider(IFinancialDataProvider):
    """Alpha Vantage implementation of financial statement and quote access."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise AlphaVantageError("ALPHA_VANTAGE_API_KEY is required.")
        self._fundamentals = FundamentalData(key=api_key, output_format="pandas")
        self._timeseries = TimeSeries(key=api_key, output_format="pandas")

    @staticmethod
    def _normalize_response(data: Any, context: str) -> pd.DataFrame:
        if isinstance(data, tuple):
            data = data[0]
        if isinstance(data, pd.DataFrame):
            if data.empty:
                raise AlphaVantageError(f"{context}: empty dataframe returned.")
            if "Note" in data.columns:
                note = str(data["Note"].iloc[0])
                raise AlphaVantageError(f"{context}: rate limit or API note — {note}")
            return data
        if isinstance(data, dict):
            if "Note" in data:
                raise AlphaVantageError(f"{context}: {data['Note']}")
            if "Error Message" in data:
                raise AlphaVantageError(f"{context}: {data['Error Message']}")
            if "Information" in data:
                raise AlphaVantageError(f"{context}: {data['Information']}")
            return pd.DataFrame([data])
        raise AlphaVantageError(f"{context}: unexpected response type {type(data)!r}")

    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame:
        symbol = symbol.upper().strip()
        if period.lower().startswith("q"):
            data, _ = self._fundamentals.get_balance_sheet_quarterly(symbol=symbol)
        else:
            data, _ = self._fundamentals.get_balance_sheet_annual(symbol=symbol)
        return self._normalize_response(data, f"balance sheet ({symbol})")

    def get_income_statement(self, symbol: str, period: str) -> pd.DataFrame:
        symbol = symbol.upper().strip()
        if period.lower().startswith("q"):
            data, _ = self._fundamentals.get_income_statement_quarterly(symbol=symbol)
        else:
            data, _ = self._fundamentals.get_income_statement_annual(symbol=symbol)
        return self._normalize_response(data, f"income statement ({symbol})")

    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame:
        symbol = symbol.upper().strip()
        if period.lower().startswith("q"):
            data, _ = self._fundamentals.get_cash_flow_quarterly(symbol=symbol)
        else:
            data, _ = self._fundamentals.get_cash_flow_annual(symbol=symbol)
        return self._normalize_response(data, f"cash flow ({symbol})")

    def get_overview(self, symbol: str) -> dict:
        symbol = symbol.upper().strip()
        data, _ = self._fundamentals.get_company_overview(symbol=symbol)
        if isinstance(data, pd.DataFrame):
            if data.empty:
                raise AlphaVantageError(f"overview ({symbol}): empty response")
            row = data.iloc[0].to_dict()
        elif isinstance(data, dict):
            row = data
        else:
            raise AlphaVantageError(f"overview ({symbol}): unexpected payload")
        if row.get("Note"):
            raise AlphaVantageError(str(row["Note"]))
        if row.get("Error Message"):
            raise AlphaVantageError(str(row["Error Message"]))
        return {str(k): v for k, v in row.items()}

    def get_latest_price(self, symbol: str) -> float:
        symbol = symbol.upper().strip()
        data, _ = self._timeseries.get_quote_endpoint(symbol=symbol)
        if isinstance(data, pd.DataFrame):
            if data.empty:
                raise AlphaVantageError(f"quote ({symbol}): empty response")
            row = data.iloc[0]
            price_key = "05. price" if "05. price" in row.index else row.index[-1]
            return float(row[price_key])
        if isinstance(data, dict):
            if "Global Quote" in data and data["Global Quote"]:
                return float(data["Global Quote"]["05. price"])
            if "Note" in data:
                raise AlphaVantageError(str(data["Note"]))
        raise AlphaVantageError(f"quote ({symbol}): could not parse price")
