from __future__ import annotations

import pandas as pd

from src.core.interfaces import IFundamentalProvider, IFinancialDataProvider
from src.core.markdown import dataframe_to_markdown, dict_to_markdown


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _latest_row(df: pd.DataFrame) -> pd.Series:
    if "fiscalDateEnding" in df.columns:
        ordered = df.sort_values("fiscalDateEnding", ascending=False)
        return ordered.iloc[0]
    return df.iloc[0]


def fetch_income_statement(
    provider: IFinancialDataProvider, symbol: str, period: str
) -> str:
    df = provider.get_income_statement(symbol, period)
    return f"## Income Statement — {symbol.upper()} ({period})\n\n{dataframe_to_markdown(df)}"


def fetch_balance_sheet(
    provider: IFinancialDataProvider, symbol: str, period: str
) -> str:
    df = provider.get_balance_sheet(symbol, period)
    return f"## Balance Sheet — {symbol.upper()} ({period})\n\n{dataframe_to_markdown(df)}"


def fetch_cash_flow(provider: IFinancialDataProvider, symbol: str, period: str) -> str:
    df = provider.get_cash_flow(symbol, period)
    return f"## Cash Flow — {symbol.upper()} ({period})\n\n{dataframe_to_markdown(df)}"


def compute_key_ratios(
    provider: IFundamentalProvider, symbol: str, period: str = "annual"
) -> str:
    symbol = symbol.upper().strip()
    balance = provider.get_balance_sheet(symbol, period)
    income = provider.get_income_statement(symbol, period)
    cashflow = provider.get_cash_flow(symbol, period)
    overview = provider.get_overview(symbol)

    b = _latest_row(balance)
    i = _latest_row(income)
    c = _latest_row(cashflow)

    total_current_assets = _coerce_float(b.get("totalCurrentAssets"))
    total_current_liabilities = _coerce_float(b.get("totalCurrentLiabilities"))
    inventory = _coerce_float(b.get("inventory")) or 0.0
    total_assets = _coerce_float(b.get("totalAssets"))
    total_liabilities = _coerce_float(b.get("totalLiabilities"))
    total_shareholder_equity = _coerce_float(b.get("totalShareholderEquity"))
    total_revenue = _coerce_float(i.get("totalRevenue"))
    gross_profit = _coerce_float(i.get("grossProfit"))
    operating_income = _coerce_float(i.get("operatingIncome"))
    net_income = _coerce_float(i.get("netIncome"))
    operating_cashflow = _coerce_float(c.get("operatingCashflow"))
    capex = _coerce_float(c.get("capitalExpenditures")) or 0.0

    current_ratio = (
        total_current_assets / total_current_liabilities
        if total_current_assets and total_current_liabilities
        else None
    )
    quick_ratio = (
        (total_current_assets - inventory) / total_current_liabilities
        if total_current_assets and total_current_liabilities
        else None
    )
    debt_to_equity = (
        total_liabilities / total_shareholder_equity
        if total_liabilities and total_shareholder_equity
        else None
    )
    gross_margin = gross_profit / total_revenue if gross_profit and total_revenue else None
    operating_margin = (
        operating_income / total_revenue if operating_income and total_revenue else None
    )
    net_margin = net_income / total_revenue if net_income and total_revenue else None
    roa = net_income / total_assets if net_income and total_assets else None
    roe = (
        net_income / total_shareholder_equity
        if net_income and total_shareholder_equity
        else None
    )
    free_cash_flow = (
        operating_cashflow - abs(capex) if operating_cashflow is not None else None
    )

    ratios = {
        "Current Ratio": current_ratio,
        "Quick Ratio": quick_ratio,
        "Debt-to-Equity": debt_to_equity,
        "Gross Margin": gross_margin,
        "Operating Margin": operating_margin,
        "Net Margin": net_margin,
        "ROA": roa,
        "ROE": roe,
        "Free Cash Flow (latest)": free_cash_flow,
        "Market Cap (overview)": overview.get("MarketCapitalization"),
        "Sector": overview.get("Sector"),
        "Industry": overview.get("Industry"),
    }

    table = "| Ratio | Value |\n| --- | --- |"
    for name, value in ratios.items():
        if isinstance(value, float):
            display = f"{value:,.4f}"
        else:
            display = str(value) if value is not None else "N/A"
        table += f"\n| {name} | {display} |"

    return f"## Key Ratios — {symbol}\n\n{table}\n\n### Company Overview\n\n{dict_to_markdown({k: overview.get(k) for k in ('Name', 'Symbol', 'Exchange', 'Currency') if overview.get(k)})}"
