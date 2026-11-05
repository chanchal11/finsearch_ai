"""Financial Modeling Prep adapter (``/stable`` API).

Needs ``FMP_API_KEY``. Translates FMP payloads into the canonical contract defined in
``src.providers.schema`` so the rest of the app is unaware of the vendor.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx
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

DEFAULT_BASE_URL = "https://financialmodelingprep.com/stable"

INCOME_MAP: FieldMap = {
    "totalRevenue": ("revenue",),
    "grossProfit": ("grossProfit",),
    "operatingIncome": ("operatingIncome",),
    "netIncome": ("netIncome", "bottomLineNetIncome"),
}
BALANCE_MAP: FieldMap = {
    "totalCurrentAssets": ("totalCurrentAssets",),
    "totalCurrentLiabilities": ("totalCurrentLiabilities",),
    "inventory": ("inventory",),
    "totalAssets": ("totalAssets",),
    "totalLiabilities": ("totalLiabilities",),
    "totalShareholderEquity": (
        "totalStockholdersEquity",
        "totalEquity",
    ),
    "shortLongTermDebtTotal": ("totalDebt",),
    "longTermDebt": ("longTermDebt",),
    "cashAndCashEquivalentsAtCarryingValue": ("cashAndCashEquivalents",),
    "cashAndShortTermInvestments": ("cashAndShortTermInvestments",),
}
CASHFLOW_MAP: FieldMap = {
    "operatingCashflow": (
        "operatingCashFlow",
        "netCashProvidedByOperatingActivities",
    ),
    "capitalExpenditures": (
        "capitalExpenditure",
        "investmentsInPropertyPlantAndEquipment",
    ),
}
PROFILE_MAP: FieldMap = {
    "Name": ("companyName",),
    "Symbol": ("symbol",),
    "Exchange": ("exchange", "exchangeFullName"),
    "Currency": ("currency",),
    "Sector": ("sector",),
    "Industry": ("industry",),
    "MarketCapitalization": ("marketCap", "mktCap"),
}
RATIO_MAP: FieldMap = {
    "PERatio": ("priceToEarningsRatioTTM", "peRatioTTM", "priceEarningsRatioTTM"),
    "PriceToBookRatio": ("priceToBookRatioTTM", "priceBookValueRatioTTM"),
    "PriceToSalesRatioTTM": ("priceToSalesRatioTTM",),
}
KEY_METRIC_MAP: FieldMap = {
    "EVToEBITDA": ("evToEBITDATTM", "enterpriseValueOverEBITDATTM"),
}


def _period_param(period: str) -> str:
    return "quarter" if period.lower().startswith("q") else "annual"


def income_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return statement_frame(((r.get("date", ""), r) for r in rows), INCOME_MAP)


def balance_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return statement_frame(((r.get("date", ""), r) for r in rows), BALANCE_MAP)


def cashflow_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return statement_frame(((r.get("date", ""), r) for r in rows), CASHFLOW_MAP)


def overview_record(
    profile: dict[str, Any],
    ratios: dict[str, Any] | None = None,
    key_metrics: dict[str, Any] | None = None,
    income_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Merge FMP profile, TTM ratios, and metrics into an Alpha Vantage style overview."""
    record = map_record(profile, PROFILE_MAP)
    record.update(map_record(ratios or {}, RATIO_MAP))
    record.update(map_record(key_metrics or {}, KEY_METRIC_MAP))
    record["ForwardPE"] = None  # forward estimates are a paid FMP feature

    shares = pick(profile, ("sharesOutstanding",))
    market_cap, price = (
        pick(profile, ("marketCap", "mktCap")),
        pick(profile, ("price",)),
    )
    if shares is None and market_cap and price:
        shares = float(market_cap) / float(price)
    if shares is None and income_rows:
        shares = pick(
            income_rows[0], ("weightedAverageShsOutDil", "weightedAverageShsOut")
        )
    record["SharesOutstanding"] = shares
    return record


def weekly_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Daily EOD rows (any order) to ascending week-ending closes."""
    daily = pd.DataFrame(
        [{"date": r.get("date"), "close": pick(r, ("adjClose", "close"))} for r in rows]
    )
    return weekly_closes(daily)


class FmpProvider(IFinancialDataProvider):
    """Financial Modeling Prep implementation of ``IFinancialDataProvider``."""

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        client: httpx.Client | None = None,
        statement_limit: int = 5,
        history_years: int = 3,
    ) -> None:
        if not api_key:
            raise FinancialDataError(
                "FMP_API_KEY is required when FINANCIAL_DATA_PROVIDER=fmp."
            )
        self._api_key = api_key
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._client = client or httpx.Client(timeout=20.0)
        self._limit = statement_limit
        self._history_years = history_years

    # -- transport -------------------------------------------------------------

    def _get(self, path: str, context: str, **params: Any) -> Any:
        url = f"{self._base_url}/{path}"
        try:
            response = self._client.get(url, params={**params, "apikey": self._api_key})
        except httpx.HTTPError as exc:
            raise FinancialDataError(f"FMP {context}: request failed ({exc}).") from exc

        body: Any
        try:
            body = response.json()
        except ValueError:
            body = response.text.strip()

        if response.status_code >= 400:
            raise FinancialDataError(
                f"FMP {context}: HTTP {response.status_code} - {_message(body)}"
            )
        if isinstance(body, dict) and ("Error Message" in body or "error" in body):
            raise FinancialDataError(f"FMP {context}: {_message(body)}")
        if isinstance(body, str):
            # FMP reports plan limits and bad keys as plain text with HTTP 200.
            raise FinancialDataError(f"FMP {context}: {body[:200]}")
        return body

    def _records(self, path: str, context: str, **params: Any) -> list[dict[str, Any]]:
        body = self._get(path, context, **params)
        if isinstance(body, dict):
            body = body.get("historical", [body])
        if not body:
            raise FinancialDataError(
                f"FMP {context}: no data returned (symbol unknown or not on your plan)."
            )
        return [row for row in body if isinstance(row, dict)]

    def _statement(
        self, path: str, symbol: str, period: str, label: str
    ) -> list[dict[str, Any]]:
        symbol = symbol.upper().strip()
        return self._records(
            path,
            f"{label} ({symbol})",
            symbol=symbol,
            period=_period_param(period),
            limit=self._limit,
        )

    # -- IFinancialDataProvider ---------------------------------------------------

    def get_income_statement(self, symbol: str, period: str) -> pd.DataFrame:
        rows = self._statement("income-statement", symbol, period, "income statement")
        return require_rows(income_frame(rows), "FMP income statement")

    def get_balance_sheet(self, symbol: str, period: str) -> pd.DataFrame:
        rows = self._statement(
            "balance-sheet-statement", symbol, period, "balance sheet"
        )
        return require_rows(balance_frame(rows), "FMP balance sheet")

    def get_cash_flow(self, symbol: str, period: str) -> pd.DataFrame:
        rows = self._statement("cash-flow-statement", symbol, period, "cash flow")
        return require_rows(cashflow_frame(rows), "FMP cash flow")

    def get_overview(self, symbol: str) -> dict:
        symbol = symbol.upper().strip()
        profile = self._records("profile", f"profile ({symbol})", symbol=symbol)[0]
        ratios = self._optional("ratios-ttm", symbol)
        metrics = self._optional("key-metrics-ttm", symbol)
        income_rows: list[dict[str, Any]] | None = None
        if pick(profile, ("sharesOutstanding",)) is None and not (
            pick(profile, ("marketCap", "mktCap")) and pick(profile, ("price",))
        ):
            income_rows = self._optional_rows("income-statement", symbol, limit=1)
        return overview_record(profile, ratios, metrics, income_rows)

    def get_latest_price(self, symbol: str) -> float:
        symbol = symbol.upper().strip()
        quote = self._records("quote", f"quote ({symbol})", symbol=symbol)[0]
        price = pick(quote, ("price",))
        if price is None:
            raise FinancialDataError(f"FMP quote ({symbol}): price missing.")
        return float(price)

    def get_weekly_prices(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper().strip()
        start = date.today() - timedelta(days=365 * self._history_years)
        rows = self._records(
            "historical-price-eod/full",
            f"prices ({symbol})",
            symbol=symbol,
            **{"from": start.isoformat(), "to": date.today().isoformat()},
        )
        return require_rows(weekly_frame(rows), f"FMP prices ({symbol})")

    # -- optional enrichment -------------------------------------------------------

    def _optional_rows(
        self, path: str, symbol: str, **params: Any
    ) -> list[dict[str, Any]] | None:
        try:
            return self._records(path, f"{path} ({symbol})", symbol=symbol, **params)
        except FinancialDataError as exc:
            logger.warning("FMP optional endpoint skipped: %s", exc)
            return None

    def _optional(self, path: str, symbol: str) -> dict[str, Any] | None:
        rows = self._optional_rows(path, symbol)
        return rows[0] if rows else None


def _message(body: Any) -> str:
    if isinstance(body, dict):
        return str(body.get("Error Message") or body.get("error") or body)[:200]
    return str(body)[:200]
