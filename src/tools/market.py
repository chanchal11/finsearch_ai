from __future__ import annotations

import math

import pandas as pd

from src.core.interfaces import IMarketDataProvider
from src.domain.snapshot import PriceStats

WEEKS_PER_YEAR = 52


def _window(prices: pd.DataFrame, weeks: int) -> pd.DataFrame:
    frame = prices.sort_values("date").reset_index(drop=True)
    return frame.tail(weeks + 1) if weeks > 0 else frame


def compute_price_stats(symbol: str, prices: pd.DataFrame, weeks: int = 104) -> PriceStats:
    """Return, volatility, drawdown, and 52-week range from weekly closes."""
    frame = _window(prices, weeks)
    if len(frame) < 2:
        raise ValueError(f"Not enough price history for {symbol}.")
    closes = frame["close"].astype(float)
    last = float(closes.iloc[-1])
    total_return = last / float(closes.iloc[0]) - 1

    weekly_returns = closes.pct_change().dropna()
    volatility = (
        float(weekly_returns.std() * math.sqrt(WEEKS_PER_YEAR))
        if len(weekly_returns) > 1
        else None
    )
    drawdown = float((closes / closes.cummax() - 1).min())

    last_year = closes.tail(WEEKS_PER_YEAR)
    high = float(last_year.max())
    low = float(last_year.min())
    return PriceStats(
        symbol=symbol.upper(),
        last_price=last,
        total_return=total_return,
        annualized_volatility=volatility,
        max_drawdown=drawdown,
        high_52w=high,
        low_52w=low,
        pct_from_52w_high=last / high - 1 if high else None,
        weeks=len(frame) - 1,
    )


def indexed_series(prices: pd.DataFrame, weeks: int) -> list[tuple[str, float]]:
    """Closes rebased to 100 at the start of the window, as (iso date, value) pairs."""
    frame = _window(prices, weeks)
    base = float(frame["close"].iloc[0])
    return [
        (row.date.strftime("%Y-%m-%d"), float(row.close) / base * 100)
        for row in frame.itertuples()
    ]


def get_price_performance(
    provider: IMarketDataProvider, symbol: str, peers: str = "", weeks: int = 104
) -> str:
    """Markdown comparison of price behaviour for a ticker against its peers."""
    tickers = [symbol.upper().strip()] + [
        p.strip().upper() for p in peers.split(",") if p.strip()
    ]
    rows: list[str] = []
    errors: list[str] = []
    for ticker in dict.fromkeys(tickers):
        try:
            stats = compute_price_stats(ticker, provider.get_weekly_prices(ticker), weeks)
        except Exception as exc:  # noqa: BLE001 - report per-ticker data gaps to the agent
            errors.append(f"- {ticker}: {exc}")
            continue
        vol = (
            f"{stats.annualized_volatility:.1%}"
            if stats.annualized_volatility is not None
            else "N/A"
        )
        from_high = (
            f"{stats.pct_from_52w_high:+.1%}" if stats.pct_from_52w_high is not None else "N/A"
        )
        rows.append(
            f"| {ticker} | {stats.last_price:,.2f} | {stats.total_return:+.1%} | {vol} "
            f"| {stats.max_drawdown:.1%} | {from_high} |"
        )
    if not rows:
        detail = "\n".join(errors) or "_No data._"
        return f"## Price Performance\n\nNo price history available.\n\n{detail}"
    table = (
        f"| Ticker | Last | Return ({weeks}w) | Volatility (ann.) | Max drawdown | vs 52w high |\n"
        "| --- | --- | --- | --- | --- | --- |\n" + "\n".join(rows)
    )
    footer = ("\n\n### Data gaps\n\n" + "\n".join(errors)) if errors else ""
    return f"## Price Performance\n\n{table}{footer}"
