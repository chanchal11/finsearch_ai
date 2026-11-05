from __future__ import annotations

import pandas as pd

from src.core.interfaces import IFundamentalProvider, IFinancialDataProvider
from src.core.markdown import dataframe_to_markdown, dict_to_markdown
from src.domain.snapshot import AnnualPoint


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number else None  # NaN becomes missing
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


def annual_history(
    provider: IFundamentalProvider, symbol: str, years: int = 5
) -> list[AnnualPoint]:
    """Oldest-to-newest annual revenue, margin inputs, and cash flow for a ticker."""
    income = provider.get_income_statement(symbol, "annual")
    cashflow = provider.get_cash_flow(symbol, "annual")

    cash_by_year: dict[str, pd.Series] = {}
    if "fiscalDateEnding" in cashflow.columns:
        for _, row in cashflow.iterrows():
            cash_by_year[str(row["fiscalDateEnding"])[:4]] = row

    if "fiscalDateEnding" in income.columns:
        income = income.sort_values("fiscalDateEnding", ascending=False)
    points: list[AnnualPoint] = []
    for _, row in income.head(years).iterrows():
        year = str(row.get("fiscalDateEnding", ""))[:4]
        cash = cash_by_year.get(year)
        operating_cf = _coerce_float(cash.get("operatingCashflow")) if cash is not None else None
        capex = _coerce_float(cash.get("capitalExpenditures")) if cash is not None else None
        fcf = operating_cf - abs(capex or 0.0) if operating_cf is not None else None
        points.append(
            AnnualPoint(
                fiscal_year=year,
                revenue=_coerce_float(row.get("totalRevenue")),
                gross_profit=_coerce_float(row.get("grossProfit")),
                operating_income=_coerce_float(row.get("operatingIncome")),
                net_income=_coerce_float(row.get("netIncome")),
                operating_cash_flow=operating_cf,
                capex=abs(capex) if capex is not None else None,
                free_cash_flow=fcf,
            )
        )
    return list(reversed(points))


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "N/A"
    magnitude = abs(value)
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if magnitude >= size:
            return f"{value / size:,.2f}{unit}"
    return f"{value:,.0f}"


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "N/A"


def fetch_financial_trends(
    provider: IFundamentalProvider, symbol: str, years: int = 5
) -> str:
    """Multi-year margin and earnings-quality table for fundamental and risk work."""
    symbol = symbol.upper().strip()
    points = annual_history(provider, symbol, years)
    if not points:
        return f"## Financial Trends — {symbol}\n\n_No annual history available._"

    table = (
        "| Year | Revenue | Rev growth | Gross margin | Operating margin | Net margin "
        "| Net income | Operating CF | FCF | FCF / Net income |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
    )
    previous: AnnualPoint | None = None
    for point in points:
        growth = (
            point.revenue / previous.revenue - 1
            if previous and previous.revenue and point.revenue is not None
            else None
        )
        conversion = point.cash_conversion
        table += (
            f"\n| {point.fiscal_year} | {_fmt_money(point.revenue)} | {_fmt_pct(growth)} "
            f"| {_fmt_pct(point.gross_margin)} | {_fmt_pct(point.operating_margin)} "
            f"| {_fmt_pct(point.net_margin)} | {_fmt_money(point.net_income)} "
            f"| {_fmt_money(point.operating_cash_flow)} | {_fmt_money(point.free_cash_flow)} "
            f"| {f'{conversion:.2f}x' if conversion is not None else 'N/A'} |"
        )
        previous = point

    notes: list[str] = []
    latest = points[-1]
    if latest.cash_conversion is not None and latest.cash_conversion < 0.8:
        notes.append(
            "Latest free cash flow is below 80% of net income; check accruals and capex intensity."
        )
    if len(points) >= 2:
        first, last = points[0], points[-1]
        if (
            first.operating_margin is not None
            and last.operating_margin is not None
            and last.operating_margin < first.operating_margin
        ):
            notes.append("Operating margin is lower than at the start of the window.")
    body = "\n".join(f"- {note}" for note in notes) or "- No automatic flags raised."
    return f"## Financial Trends — {symbol}\n\n{table}\n\n### Flags\n\n{body}"


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
