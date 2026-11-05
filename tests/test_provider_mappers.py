"""Offline checks that every adapter emits the columns the tools read.

FMP runs through its real HTTP code path against a mock transport; Yahoo runs against a
fake ``Ticker``. No network access is needed.
"""

from __future__ import annotations

from typing import ClassVar

import httpx
import pandas as pd
import pytest

from src.config import Settings
from src.core.interfaces import IFinancialDataProvider
from src.providers.factory import build_financial_provider
from src.providers.fmp import FmpProvider
from src.providers.schema import (
    BALANCE_FIELDS,
    CASHFLOW_FIELDS,
    DATE_COLUMN,
    INCOME_FIELDS,
    OVERVIEW_FIELDS,
    FinancialDataError,
)
from src.providers.yfinance_provider import YFinanceProvider
from src.tools.fundamentals import annual_history
from src.tools.valuation import dcf_scenarios

YEARS = ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"]


# -- canned FMP payloads --------------------------------------------------------------


def _fmp_rows(builder) -> list[dict]:
    return [builder(i, d) for i, d in enumerate(YEARS)]


FMP_PAYLOADS = {
    "income-statement": _fmp_rows(
        lambda i, d: {
            "date": d,
            "revenue": 1000 - 100 * i,
            "grossProfit": 500 - 40 * i,
            "operatingIncome": 250 - 20 * i,
            "netIncome": 200 - 15 * i,
            "weightedAverageShsOut": 100,
        }
    ),
    "balance-sheet-statement": _fmp_rows(
        lambda i, d: {
            "date": d,
            "totalCurrentAssets": 400,
            "totalCurrentLiabilities": 200,
            "inventory": 50,
            "totalAssets": 1500,
            "totalLiabilities": 700,
            "totalStockholdersEquity": 800,
            "totalDebt": 300,
            "longTermDebt": 250,
            "cashAndCashEquivalents": 120,
            "cashAndShortTermInvestments": 180,
        }
    ),
    "cash-flow-statement": _fmp_rows(
        lambda i, d: {
            "date": d,
            "operatingCashFlow": 300 - 20 * i,
            "capitalExpenditure": -(60 + i),
        }
    ),
    "profile": [
        {
            "symbol": "ACME",
            "companyName": "Acme Corp",
            "exchange": "NASDAQ",
            "currency": "USD",
            "sector": "Technology",
            "industry": "Software",
            "marketCap": 10_000,
            "price": 100,
        }
    ],
    "quote": [{"symbol": "ACME", "price": 101.5}],
    "ratios-ttm": [
        {
            "priceToEarningsRatioTTM": 25.0,
            "priceToBookRatioTTM": 5.0,
            "priceToSalesRatioTTM": 8.0,
        }
    ],
    "key-metrics-ttm": [{"evToEBITDATTM": 18.0}],
    "historical-price-eod/full": [
        {"symbol": "ACME", "date": d.strftime("%Y-%m-%d"), "close": 100 + i}
        for i, d in enumerate(pd.bdate_range("2025-01-01", periods=60))
    ],
}


def _fmp_provider(overrides: dict | None = None) -> FmpProvider:
    payloads = {**FMP_PAYLOADS, **(overrides or {})}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["apikey"] == "test-key"
        path = request.url.path.removeprefix("/stable/")
        body = payloads[path]
        if isinstance(body, httpx.Response):
            return body
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return FmpProvider("test-key", client=client)


# -- fake Yahoo ticker -----------------------------------------------------------------


def _yahoo_frame(rows: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, index=pd.to_datetime(YEARS)).T


class _FakeTicker:
    income_stmt = _yahoo_frame(
        {
            "Total Revenue": [1000, 900, 800, 700],
            "Gross Profit": [500, 460, 420, float("nan")],
            "Operating Income": [250, 230, 210, 190],
            "Net Income": [200, 185, 170, 155],
        }
    )
    quarterly_income_stmt = income_stmt
    balance_sheet = _yahoo_frame(
        {
            "Current Assets": [400] * 4,
            "Current Liabilities": [200] * 4,
            "Inventory": [50] * 4,
            "Total Assets": [1500] * 4,
            "Total Liabilities Net Minority Interest": [700] * 4,
            "Stockholders Equity": [800] * 4,
            "Total Debt": [300] * 4,
            "Long Term Debt": [250] * 4,
            "Cash And Cash Equivalents": [120] * 4,
            "Cash Cash Equivalents And Short Term Investments": [180] * 4,
        }
    )
    quarterly_balance_sheet = balance_sheet
    cashflow = _yahoo_frame(
        {
            "Operating Cash Flow": [300, 280, 260, 240],
            "Capital Expenditure": [-60, -61, -62, -63],
        }
    )
    quarterly_cashflow = cashflow
    info: ClassVar[dict] = {
        "symbol": "ACME",
        "longName": "Acme Corp",
        "fullExchangeName": "NasdaqGS",
        "currency": "USD",
        "sector": "Technology",
        "industry": "Software",
        "marketCap": 10_000,
        "sharesOutstanding": 100,
        "trailingPE": 25.0,
        "forwardPE": 21.0,
        "enterpriseToEbitda": 18.0,
        "priceToBook": 5.0,
        "priceToSalesTrailing12Months": 8.0,
    }
    fast_info: ClassVar[dict] = {"last_price": 101.5}

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, **_: object) -> pd.DataFrame:
        index = pd.date_range(
            "2024-01-01", periods=80, freq="W-MON", tz="America/New_York"
        )
        return pd.DataFrame({"Close": [100 + i for i in range(80)]}, index=index)


def _yahoo_provider() -> YFinanceProvider:
    return YFinanceProvider(ticker_factory=_FakeTicker)


@pytest.fixture(params=["fmp", "yfinance"])
def provider(request: pytest.FixtureRequest) -> IFinancialDataProvider:
    return _fmp_provider() if request.param == "fmp" else _yahoo_provider()


# -- contract tests ----------------------------------------------------------------------


@pytest.mark.parametrize("period", ["annual", "quarterly"])
def test_statements_expose_canonical_columns(provider, period):
    income = provider.get_income_statement("acme", period)
    balance = provider.get_balance_sheet("acme", period)
    cashflow = provider.get_cash_flow("acme", period)

    for frame, fields in (
        (income, INCOME_FIELDS),
        (balance, BALANCE_FIELDS),
        (cashflow, CASHFLOW_FIELDS),
    ):
        assert set(fields) | {DATE_COLUMN} <= set(frame.columns)
        assert list(frame[DATE_COLUMN]) == sorted(frame[DATE_COLUMN], reverse=True)


def test_overview_has_every_key_the_tools_read(provider):
    overview = provider.get_overview("acme")
    assert set(OVERVIEW_FIELDS) <= set(overview)
    assert overview["Name"] == "Acme Corp"
    assert overview["SharesOutstanding"] == pytest.approx(100)
    assert overview["PERatio"] == pytest.approx(25.0)
    assert overview["EVToEBITDA"] == pytest.approx(18.0)


def test_price_and_weekly_series(provider):
    assert provider.get_latest_price("acme") == pytest.approx(101.5)
    weekly = provider.get_weekly_prices("acme")
    assert list(weekly.columns) == ["date", "close"]
    assert pd.api.types.is_datetime64_any_dtype(weekly["date"])
    assert weekly["date"].is_monotonic_increasing
    assert weekly["close"].notna().all()


def test_tools_run_unchanged_on_every_adapter(provider):
    points = annual_history(provider, "ACME", years=4)
    assert [p.fiscal_year for p in points] == sorted(p.fiscal_year for p in points)
    assert points[-1].revenue == pytest.approx(1000)
    assert points[-1].free_cash_flow == pytest.approx(240)

    bear, base, bull = dcf_scenarios(provider, "ACME")
    assert bear.intrinsic_price < base.intrinsic_price < bull.intrinsic_price
    assert base.shares_outstanding == pytest.approx(100)


def test_missing_yahoo_values_become_none_not_nan():
    income = _yahoo_provider().get_income_statement("acme", "annual")
    assert income["grossProfit"].isna().sum() == 1
    assert annual_history(_yahoo_provider(), "ACME", years=4)[0].gross_profit is None


# -- FMP failure modes ----------------------------------------------------------------------


def test_fmp_requires_a_key():
    with pytest.raises(FinancialDataError, match="FMP_API_KEY"):
        FmpProvider("")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, json={"Error Message": "Invalid API KEY."}),
        httpx.Response(200, text="Premium Query Parameter: not on your plan"),
        httpx.Response(200, json=[]),
    ],
)
def test_fmp_errors_are_clear(response):
    provider = _fmp_provider({"income-statement": response})
    with pytest.raises(FinancialDataError, match="FMP"):
        provider.get_income_statement("acme", "annual")


def test_fmp_overview_survives_missing_optional_endpoints():
    provider = _fmp_provider(
        {
            "ratios-ttm": httpx.Response(402, text="Premium"),
            "key-metrics-ttm": httpx.Response(402, text="Premium"),
        }
    )
    overview = provider.get_overview("acme")
    assert overview["Name"] == "Acme Corp"
    assert overview["PERatio"] is None
    assert overview["SharesOutstanding"] == pytest.approx(100)  # marketCap / price


# -- factory ---------------------------------------------------------------------------------


def _settings(**values: str) -> Settings:
    return Settings(_env_file=None, **values)


def test_factory_selects_each_vendor():
    assert isinstance(
        build_financial_provider(_settings(FINANCIAL_DATA_PROVIDER="yfinance")),
        YFinanceProvider,
    )
    assert isinstance(
        build_financial_provider(
            _settings(FINANCIAL_DATA_PROVIDER=" FMP ", FMP_API_KEY="k")
        ),
        FmpProvider,
    )


def test_factory_defaults_to_yfinance():
    assert isinstance(build_financial_provider(_settings()), YFinanceProvider)


def test_factory_rejects_unknown_vendor():
    with pytest.raises(ValueError, match=r"yfinance \| fmp \| alphavantage"):
        build_financial_provider(_settings(FINANCIAL_DATA_PROVIDER="bloomberg"))


def test_factory_reports_missing_fmp_key():
    with pytest.raises(FinancialDataError, match="FMP_API_KEY"):
        build_financial_provider(_settings(FINANCIAL_DATA_PROVIDER="fmp"))
