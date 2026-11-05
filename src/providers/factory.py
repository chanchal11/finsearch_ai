"""Select the financial-data vendor from ``FINANCIAL_DATA_PROVIDER``.

This is the only module that constructs vendor clients. Adding a vendor means adding
one adapter and one entry in ``_BUILDERS``; tools, agents, and UI stay unchanged.
"""

from __future__ import annotations

from collections.abc import Callable

from src.config import Settings
from src.core.interfaces import IFinancialDataProvider


def _build_yfinance(settings: Settings) -> IFinancialDataProvider:
    from src.providers.yfinance_provider import YFinanceProvider

    return YFinanceProvider()


def _build_fmp(settings: Settings) -> IFinancialDataProvider:
    from src.providers.fmp import FmpProvider

    return FmpProvider(settings.fmp_api_key, settings.fmp_base_url)


def _build_alphavantage(settings: Settings) -> IFinancialDataProvider:
    from src.providers.alpha_vantage import AlphaVantageProvider

    return AlphaVantageProvider(settings.alpha_vantage_api_key)


_BUILDERS: dict[str, Callable[[Settings], IFinancialDataProvider]] = {
    "yfinance": _build_yfinance,
    "fmp": _build_fmp,
    "alphavantage": _build_alphavantage,
}


def available_providers() -> tuple[str, ...]:
    return tuple(_BUILDERS)


def build_financial_provider(settings: Settings) -> IFinancialDataProvider:
    name = settings.financial_source
    builder = _BUILDERS.get(name)
    if builder is None:
        allowed = " | ".join(_BUILDERS)
        raise ValueError(
            f"Unknown FINANCIAL_DATA_PROVIDER={settings.financial_data_provider!r}. "
            f"Use one of: {allowed}."
        )
    return builder(settings)
