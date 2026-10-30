from __future__ import annotations

import pandas as pd

from src.core.interfaces import IFinancialDataProvider, IValuationProvider
from src.core.markdown import dict_to_markdown


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _latest_fcf(provider: IValuationProvider, symbol: str) -> float:
    cashflow = provider.get_cash_flow(symbol, "annual")
    if cashflow.empty:
        raise ValueError(f"No cash flow history for {symbol}")
    if "fiscalDateEnding" in cashflow.columns:
        cashflow = cashflow.sort_values("fiscalDateEnding", ascending=False)
    row = cashflow.iloc[0]
    operating = _coerce_float(row.get("operatingCashflow"))
    capex = _coerce_float(row.get("capitalExpenditures")) or 0.0
    if operating is None:
        raise ValueError(f"Missing operating cash flow for {symbol}")
    fcf = operating - abs(capex)
    if fcf <= 0:
        raise ValueError(
            f"Latest FCF for {symbol} is non-positive ({fcf:,.0f}); DCF requires positive base FCF."
        )
    return fcf


def run_dcf_model(
    provider: IFinancialDataProvider,
    symbol: str,
    *,
    growth_rate: float = 0.08,
    discount_rate: float = 0.1,
    terminal_growth_rate: float = 0.025,
    forecast_years: int = 5,
) -> str:
    symbol = symbol.upper().strip()
    if discount_rate <= terminal_growth_rate:
        raise ValueError("Discount rate must exceed terminal growth rate.")
    if forecast_years < 1 or forecast_years > 10:
        raise ValueError("forecast_years must be between 1 and 10.")

    base_fcf = _latest_fcf(provider, symbol)
    overview = provider.get_overview(symbol)
    shares = _coerce_float(overview.get("SharesOutstanding"))
    if not shares or shares <= 0:
        raise ValueError(f"Missing share count for {symbol}")

    balance = provider.get_balance_sheet(symbol, "annual")
    if "fiscalDateEnding" in balance.columns:
        balance = balance.sort_values("fiscalDateEnding", ascending=False)
    b = balance.iloc[0]
    total_debt = _coerce_float(b.get("shortLongTermDebtTotal")) or _coerce_float(
        b.get("longTermDebt")
    )
    cash = _coerce_float(b.get("cashAndCashEquivalentsAtCarryingValue")) or _coerce_float(
        b.get("cashAndShortTermInvestments")
    )
    net_debt = (total_debt or 0.0) - (cash or 0.0)

    projected: list[dict[str, float]] = []
    fcf = base_fcf
    pv_sum = 0.0
    for year in range(1, forecast_years + 1):
        fcf *= 1 + growth_rate
        pv = fcf / ((1 + discount_rate) ** year)
        pv_sum += pv
        projected.append({"year": float(year), "fcf": fcf, "pv": pv})

    terminal_fcf = fcf * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (discount_rate - terminal_growth_rate)
    pv_terminal = terminal_value / ((1 + discount_rate) ** forecast_years)
    enterprise_value = pv_sum + pv_terminal
    equity_value = enterprise_value - net_debt
    intrinsic_price = equity_value / shares
    market_price = provider.get_latest_price(symbol)
    margin_of_safety = (intrinsic_price - market_price) / market_price

    proj_md = "| Year | FCF | PV |\n| --- | --- | --- |"
    for row in projected:
        proj_md += f"\n| {int(row['year'])} | {row['fcf']:,.0f} | {row['pv']:,.0f} |"

    summary = {
        "Base FCF": base_fcf,
        "Net Debt": net_debt,
        "Enterprise Value": enterprise_value,
        "Equity Value": equity_value,
        "Shares Outstanding": shares,
        "Intrinsic Price / Share": intrinsic_price,
        "Market Price": market_price,
        "Margin of Safety": margin_of_safety,
        "Growth Rate": growth_rate,
        "Discount Rate": discount_rate,
        "Terminal Growth": terminal_growth_rate,
    }

    return (
        f"## DCF Valuation — {symbol}\n\n"
        f"{dict_to_markdown(summary)}\n\n"
        f"### Projection\n\n{proj_md}"
    )


def get_peer_multiples(provider: IFinancialDataProvider, peers: str) -> str:
    tickers = [p.strip().upper() for p in peers.split(",") if p.strip()]
    if not tickers:
        raise ValueError("Provide at least one peer ticker.")

    rows: list[dict[str, object]] = []
    for ticker in tickers:
        overview = provider.get_overview(ticker)
        rows.append(
            {
                "Symbol": ticker,
                "P/E": overview.get("PERatio"),
                "Forward P/E": overview.get("ForwardPE"),
                "EV/EBITDA": overview.get("EVToEBITDA"),
                "P/B": overview.get("PriceToBookRatio"),
                "P/S": overview.get("PriceToSalesRatioTTM"),
                "Market Cap": overview.get("MarketCapitalization"),
            }
        )

    df = pd.DataFrame(rows)
    return f"## Peer Multiples\n\n{df.to_markdown(index=False)}"
