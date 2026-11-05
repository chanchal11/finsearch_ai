from __future__ import annotations

from statistics import median

import altair as alt
import pandas as pd

from src.domain.snapshot import CommitteeScores, ResearchSnapshot
from src.tools import market

CHART_HEIGHT = 300
POSITIVE = "#2e9e6b"
NEGATIVE = "#d9534f"
TARGET = "#4c78a8"
MUTED = "#9aa5b1"
LINE_PALETTE = ["#f08c3c", "#9b7fe6", "#4cc9a4", "#e06c9f"]

RANGE_WEEKS = {"6M": 26, "1Y": 52, "2Y": 104}

MULTIPLES = {
    "Forward P/E": "forward_pe",
    "P/E": "pe",
    "EV/EBITDA": "ev_ebitda",
    "P/S": "price_to_sales",
}


def price_frame(snapshot: ResearchSnapshot, weeks: int) -> pd.DataFrame:
    """Closes for the target and peers, rebased to 100 at the start of the window."""
    rows: list[pd.DataFrame] = []
    for symbol, series in snapshot.price_history.items():
        raw = pd.DataFrame(series, columns=["date", "close"])
        raw["date"] = pd.to_datetime(raw["date"])
        indexed = market.indexed_series(raw, weeks)
        frame = pd.DataFrame(indexed, columns=["date", "indexed"])
        frame["date"] = pd.to_datetime(frame["date"])
        frame["symbol"] = symbol
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def price_stats_frame(snapshot: ResearchSnapshot, weeks: int) -> pd.DataFrame:
    rows = []
    for symbol, series in snapshot.price_history.items():
        raw = pd.DataFrame(series, columns=["date", "close"])
        raw["date"] = pd.to_datetime(raw["date"])
        try:
            stats = market.compute_price_stats(symbol, raw, weeks)
        except ValueError:
            continue
        rows.append(
            {
                "Ticker": symbol,
                "Return": stats.total_return,
                "Volatility (ann.)": stats.annualized_volatility,
                "Max drawdown": stats.max_drawdown,
                "vs 52w high": stats.pct_from_52w_high,
            }
        )
    return pd.DataFrame(rows)


def price_chart(frame: pd.DataFrame, target: str) -> alt.Chart:
    peers = [s for s in frame["symbol"].unique() if s != target]
    order = [target, *peers]
    colors = [TARGET, *LINE_PALETTE[: len(peers)]]
    return (
        alt.Chart(frame)
        .mark_line()
        .encode(
            x=alt.X("date:T", title=None),
            y=alt.Y("indexed:Q", title="Indexed price (start = 100)", scale=alt.Scale(zero=False)),
            color=alt.Color(
                "symbol:N",
                title="Ticker",
                scale=alt.Scale(domain=order, range=colors),
            ),
            strokeWidth=alt.condition(
                alt.datum.symbol == target, alt.value(3.5), alt.value(1.5)
            ),
            tooltip=[
                alt.Tooltip("symbol:N", title="Ticker"),
                alt.Tooltip("date:T", title="Week"),
                alt.Tooltip("indexed:Q", title="Indexed", format=".1f"),
            ],
        )
        .properties(height=CHART_HEIGHT)
    )


def growth_frame(snapshot: ResearchSnapshot) -> pd.DataFrame:
    rows = []
    for point in snapshot.annual:
        for label, value in (
            ("Revenue", point.revenue),
            ("Operating income", point.operating_income),
            ("Free cash flow", point.free_cash_flow),
        ):
            if value is not None:
                rows.append({"Year": point.fiscal_year, "Measure": label, "USD bn": value / 1e9})
    return pd.DataFrame(rows)


def grouped_bar_chart(frame: pd.DataFrame, category: str, value: str, series: str) -> alt.Chart:
    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X(f"{category}:N", title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=f"{series}:N",
            y=alt.Y(f"{value}:Q", title=value),
            color=alt.Color(f"{series}:N", title=None),
            tooltip=[category, series, alt.Tooltip(f"{value}:Q", format=",.1f")],
        )
        .properties(height=CHART_HEIGHT)
    )


def margin_frame(snapshot: ResearchSnapshot) -> pd.DataFrame:
    rows = []
    for point in snapshot.annual:
        for label, value in (
            ("Gross", point.gross_margin),
            ("Operating", point.operating_margin),
            ("Net", point.net_margin),
        ):
            if value is not None:
                rows.append({"Year": point.fiscal_year, "Margin": label, "Value": value})
    return pd.DataFrame(rows)


def margin_chart(frame: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(frame)
        .mark_line(point=True)
        .encode(
            x=alt.X("Year:N", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Value:Q", title="Margin", axis=alt.Axis(format="%")),
            color=alt.Color("Margin:N", title=None),
            tooltip=["Year", "Margin", alt.Tooltip("Value:Q", format=".1%")],
        )
        .properties(height=CHART_HEIGHT)
    )


def earnings_quality_frame(snapshot: ResearchSnapshot) -> pd.DataFrame:
    rows = []
    for point in snapshot.annual:
        for label, value in (
            ("Net income", point.net_income),
            ("Free cash flow", point.free_cash_flow),
        ):
            if value is not None:
                rows.append({"Year": point.fiscal_year, "Measure": label, "USD bn": value / 1e9})
    return pd.DataFrame(rows)


def valuation_chart(snapshot: ResearchSnapshot) -> alt.LayerChart | None:
    if not snapshot.scenarios:
        return None
    price = snapshot.scenarios[0].market_price
    frame = pd.DataFrame(
        [
            {
                "Scenario": s.label,
                "Intrinsic value": s.intrinsic_price,
                "Margin of safety": s.margin_of_safety,
                "Above price": s.intrinsic_price >= price,
            }
            for s in snapshot.scenarios
        ]
    )
    bars = (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X("Scenario:N", sort=["Bear", "Base", "Bull"], title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y("Intrinsic value:Q", title="Intrinsic value per share"),
            color=alt.Color(
                "Above price:N",
                scale=alt.Scale(domain=[True, False], range=[POSITIVE, NEGATIVE]),
                legend=None,
            ),
            tooltip=[
                "Scenario",
                alt.Tooltip("Intrinsic value:Q", format=",.2f"),
                alt.Tooltip("Margin of safety:Q", format="+.1%"),
            ],
        )
    )
    rule = (
        alt.Chart(pd.DataFrame({"price": [price], "label": [f"Market {price:,.2f}"]}))
        .mark_rule(strokeDash=[6, 4], color="#8a8f98", strokeWidth=2)
        .encode(y="price:Q")
    )
    text = (
        alt.Chart(pd.DataFrame({"price": [price], "label": [f"Market {price:,.2f}"]}))
        .mark_text(align="left", dx=4, dy=-8, color="#8a8f98")
        .encode(y="price:Q", text="label:N", x=alt.value(4))
    )
    return (bars + rule + text).properties(height=CHART_HEIGHT)


def multiples_frame(snapshot: ResearchSnapshot, metric: str) -> pd.DataFrame:
    attribute = MULTIPLES[metric]
    rows = [
        {
            "Ticker": m.symbol,
            "Role": "Target" if m.is_target else "Peer",
            metric: getattr(m, attribute),
        }
        for m in snapshot.multiples
        if getattr(m, attribute) is not None
    ]
    return pd.DataFrame(rows)


def multiples_chart(frame: pd.DataFrame, metric: str) -> alt.LayerChart | alt.Chart:
    bars = (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X("Ticker:N", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(f"{metric}:Q", title=metric),
            color=alt.Color(
                "Role:N",
                scale=alt.Scale(domain=["Target", "Peer"], range=[TARGET, MUTED]),
                legend=alt.Legend(title=None),
            ),
            tooltip=["Ticker", "Role", alt.Tooltip(f"{metric}:Q", format=".1f")],
        )
    )
    peers = frame.loc[frame["Role"] == "Peer", metric]
    if peers.empty:
        return bars.properties(height=CHART_HEIGHT)
    rule = (
        alt.Chart(pd.DataFrame({"median": [float(median(peers))]}))
        .mark_rule(strokeDash=[6, 4], color="#8a8f98", strokeWidth=2)
        .encode(y="median:Q")
    )
    return (bars + rule).properties(height=CHART_HEIGHT)


def scores_chart(scores: CommitteeScores) -> alt.Chart:
    frame = pd.DataFrame(scores.as_rows())
    frame["dimension"] = pd.Categorical(
        frame["dimension"],
        categories=["Fundamental", "Sentiment", "Risk", "Valuation", "Final"],
        ordered=True,
    )
    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            y=alt.Y("dimension:N", title=None, sort=None),
            x=alt.X(
                "score:Q",
                title="Score (1-10)",
                scale=alt.Scale(domain=[0, 10]),
                axis=alt.Axis(values=list(range(11))),
            ),
            color=alt.Color(
                "score:Q",
                scale=alt.Scale(domain=[1, 5.5, 10], range=[NEGATIVE, "#e8b04a", POSITIVE]),
                legend=None,
            ),
            tooltip=["dimension", "score"],
        )
        .properties(height=220)
    )
