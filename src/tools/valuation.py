from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import pandas as pd

from src.core.interfaces import IFinancialDataProvider, IValuationProvider
from src.core.markdown import dict_to_markdown
from src.domain.snapshot import DcfResult, PeerMultiple

# Explicit scenario assumptions: label -> (growth, discount, terminal growth).
DCF_SCENARIOS: dict[str, tuple[float, float, float]] = {
    "Bear": (0.04, 0.11, 0.02),
    "Base": (0.08, 0.10, 0.025),
    "Bull": (0.12, 0.09, 0.03),
}


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number == number else None  # NaN becomes missing
    text = str(value).replace(",", "").strip()
    if not text or text.lower() in {"none", "nan", "-"}:
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


@dataclass
class _DcfInputs:
    base_fcf: float
    net_debt: float
    shares: float
    market_price: float


def _load_dcf_inputs(provider: IValuationProvider, symbol: str) -> _DcfInputs:
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
    return _DcfInputs(
        base_fcf=base_fcf,
        net_debt=net_debt,
        shares=shares,
        market_price=provider.get_latest_price(symbol),
    )


def _project_dcf(
    symbol: str,
    label: str,
    inputs: _DcfInputs,
    *,
    growth_rate: float,
    discount_rate: float,
    terminal_growth_rate: float,
    forecast_years: int,
) -> DcfResult:
    if discount_rate <= terminal_growth_rate:
        raise ValueError("Discount rate must exceed terminal growth rate.")
    if forecast_years < 1 or forecast_years > 10:
        raise ValueError("forecast_years must be between 1 and 10.")

    projected: list[dict[str, float]] = []
    fcf = inputs.base_fcf
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
    equity_value = enterprise_value - inputs.net_debt
    intrinsic_price = equity_value / inputs.shares
    return DcfResult(
        symbol=symbol,
        label=label,
        base_fcf=inputs.base_fcf,
        net_debt=inputs.net_debt,
        enterprise_value=enterprise_value,
        equity_value=equity_value,
        shares_outstanding=inputs.shares,
        intrinsic_price=intrinsic_price,
        market_price=inputs.market_price,
        margin_of_safety=(intrinsic_price - inputs.market_price) / inputs.market_price,
        growth_rate=growth_rate,
        discount_rate=discount_rate,
        terminal_growth_rate=terminal_growth_rate,
        forecast_years=forecast_years,
        projection=projected,
    )


def dcf_valuation(
    provider: IValuationProvider,
    symbol: str,
    *,
    growth_rate: float = 0.08,
    discount_rate: float = 0.1,
    terminal_growth_rate: float = 0.025,
    forecast_years: int = 5,
    label: str = "Custom",
) -> DcfResult:
    symbol = symbol.upper().strip()
    inputs = _load_dcf_inputs(provider, symbol)
    return _project_dcf(
        symbol,
        label,
        inputs,
        growth_rate=growth_rate,
        discount_rate=discount_rate,
        terminal_growth_rate=terminal_growth_rate,
        forecast_years=forecast_years,
    )


def dcf_scenarios(
    provider: IValuationProvider, symbol: str, forecast_years: int = 5
) -> list[DcfResult]:
    """Bear, base, and bull DCFs from one fetch of the underlying statements."""
    symbol = symbol.upper().strip()
    inputs = _load_dcf_inputs(provider, symbol)
    return [
        _project_dcf(
            symbol,
            label,
            inputs,
            growth_rate=growth,
            discount_rate=discount,
            terminal_growth_rate=terminal,
            forecast_years=forecast_years,
        )
        for label, (growth, discount, terminal) in DCF_SCENARIOS.items()
    ]


def run_dcf_model(
    provider: IFinancialDataProvider,
    symbol: str,
    *,
    growth_rate: float = 0.08,
    discount_rate: float = 0.1,
    terminal_growth_rate: float = 0.025,
    forecast_years: int = 5,
) -> str:
    result = dcf_valuation(
        provider,
        symbol,
        growth_rate=growth_rate,
        discount_rate=discount_rate,
        terminal_growth_rate=terminal_growth_rate,
        forecast_years=forecast_years,
    )

    proj_md = "| Year | FCF | PV |\n| --- | --- | --- |"
    for row in result.projection:
        proj_md += f"\n| {int(row['year'])} | {row['fcf']:,.0f} | {row['pv']:,.0f} |"

    summary = {
        "Base FCF": result.base_fcf,
        "Net Debt": result.net_debt,
        "Enterprise Value": result.enterprise_value,
        "Equity Value": result.equity_value,
        "Shares Outstanding": result.shares_outstanding,
        "Intrinsic Price / Share": result.intrinsic_price,
        "Market Price": result.market_price,
        "Margin of Safety": result.margin_of_safety,
        "Growth Rate": result.growth_rate,
        "Discount Rate": result.discount_rate,
        "Terminal Growth": result.terminal_growth_rate,
    }

    return (
        f"## DCF Valuation — {result.symbol}\n\n"
        f"{dict_to_markdown(summary)}\n\n"
        f"### Projection\n\n{proj_md}"
    )


def run_dcf_scenarios(
    provider: IFinancialDataProvider, symbol: str, forecast_years: int = 5
) -> str:
    results = dcf_scenarios(provider, symbol, forecast_years)
    table = (
        "| Scenario | Growth | Discount rate | Terminal growth | Intrinsic price | "
        "Market price | Margin of safety |\n| --- | --- | --- | --- | --- | --- | --- |"
    )
    for r in results:
        table += (
            f"\n| {r.label} | {r.growth_rate:.1%} | {r.discount_rate:.1%} "
            f"| {r.terminal_growth_rate:.1%} | {r.intrinsic_price:,.2f} "
            f"| {r.market_price:,.2f} | {r.margin_of_safety:+.1%} |"
        )
    return (
        f"## DCF Scenarios — {results[0].symbol}\n\n{table}\n\n"
        f"Base FCF {results[0].base_fcf:,.0f}; net debt {results[0].net_debt:,.0f}; "
        f"{results[0].forecast_years}-year forecast."
    )


def peer_multiples(
    provider: IFinancialDataProvider, tickers: list[str], target: str = ""
) -> list[PeerMultiple]:
    """Valuation multiples for the target (first, flagged) and each peer."""
    target = target.upper().strip()
    ordered: list[str] = []
    for ticker in ([target] if target else []) + tickers:
        symbol = ticker.upper().strip()
        if symbol and symbol not in ordered:
            ordered.append(symbol)

    rows: list[PeerMultiple] = []
    for symbol in ordered:
        overview = provider.get_overview(symbol)
        rows.append(
            PeerMultiple(
                symbol=symbol,
                is_target=symbol == target,
                pe=_coerce_float(overview.get("PERatio")),
                forward_pe=_coerce_float(overview.get("ForwardPE")),
                ev_ebitda=_coerce_float(overview.get("EVToEBITDA")),
                price_to_book=_coerce_float(overview.get("PriceToBookRatio")),
                price_to_sales=_coerce_float(overview.get("PriceToSalesRatioTTM")),
                market_cap=_coerce_float(overview.get("MarketCapitalization")),
            )
        )
    return rows


def peer_median(rows: list[PeerMultiple], attribute: str) -> float | None:
    """Median of a multiple across peers only (the target is excluded)."""
    values = [
        getattr(row, attribute)
        for row in rows
        if not row.is_target and getattr(row, attribute) is not None
    ]
    return median(values) if values else None


def get_peer_multiples(
    provider: IFinancialDataProvider, peers: str, target: str = ""
) -> str:
    tickers = [p.strip().upper() for p in peers.split(",") if p.strip()]
    if not tickers and not target.strip():
        raise ValueError("Provide at least one peer ticker.")

    rows = peer_multiples(provider, tickers, target)
    records: list[dict[str, object]] = [
        {
            "Symbol": f"{row.symbol} (target)" if row.is_target else row.symbol,
            "P/E": row.pe,
            "Forward P/E": row.forward_pe,
            "EV/EBITDA": row.ev_ebitda,
            "P/B": row.price_to_book,
            "P/S": row.price_to_sales,
            "Market Cap": row.market_cap,
        }
        for row in rows
    ]
    if any(not row.is_target for row in rows):
        records.append(
            {
                "Symbol": "Peer median",
                "P/E": peer_median(rows, "pe"),
                "Forward P/E": peer_median(rows, "forward_pe"),
                "EV/EBITDA": peer_median(rows, "ev_ebitda"),
                "P/B": peer_median(rows, "price_to_book"),
                "P/S": peer_median(rows, "price_to_sales"),
                "Market Cap": None,
            }
        )
    df = pd.DataFrame(records)
    return f"## Peer Multiples\n\n{df.to_markdown(index=False)}"
