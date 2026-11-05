from __future__ import annotations

from statistics import median

import streamlit as st

from src.domain.insights import derive_insights
from src.ui import charts
from src.ui.format import money, number, pct
from src.ui.session import get_committee_run, get_context, get_snapshot

SEVERITY_ICON = {
    "positive": ":green[:material/check_circle:]",
    "info": ":blue[:material/info:]",
    "warning": ":orange[:material/warning:]",
    "negative": ":red[:material/error:]",
}

ctx = get_context()
snapshot = get_snapshot(ctx)

if snapshot is None:
    st.info("Enter a ticker in the sidebar and select Analyze.")
    st.stop()

has_data = bool(snapshot.annual or snapshot.scenarios or snapshot.price_history)
if not has_data:
    st.error(f"No research data could be loaded for {snapshot.symbol}.")
    for warning in snapshot.warnings:
        st.write(f"- {warning}")
    if st.button("Retry", icon=":material/refresh:"):
        get_snapshot(ctx, refresh=True)
        st.rerun()
    st.stop()

headline = snapshot.name or snapshot.symbol
details = " · ".join(part for part in (snapshot.sector.title(), snapshot.industry.title()) if part)
st.subheader(f"{headline} ({snapshot.symbol})")
if details:
    st.caption(details)

if snapshot.warnings:
    with st.expander(f"{len(snapshot.warnings)} data gap(s) in this view", icon=":material/warning:"):
        for warning in snapshot.warnings:
            st.write(f"- {warning}")
        st.caption(
            "The data provider limits requests per minute. Wait a moment, then retry; "
            "sections that already loaded stay cached."
        )
        if st.button("Retry missing data", icon=":material/refresh:"):
            get_snapshot(ctx, refresh=True)
            st.rerun()

# ---- Key figures -----------------------------------------------------------

base = snapshot.base_scenario
bear = next((s for s in snapshot.scenarios if s.label == "Bear"), None)
bull = next((s for s in snapshot.scenarios if s.label == "Bull"), None)
year_stats = charts.price_stats_frame(snapshot, 52)
own_year = year_stats[year_stats["Ticker"] == snapshot.symbol] if not year_stats.empty else year_stats
target_multiple = next((m for m in snapshot.multiples if m.is_target), None)
# Some data sources omit forward estimates; fall back to trailing P/E for the KPI.
pe_attr, pe_label = (
    ("forward_pe", "Forward P/E")
    if any(m.forward_pe for m in snapshot.multiples)
    else ("pe", "P/E (TTM)")
)
peer_forward = [
    getattr(m, pe_attr) for m in snapshot.multiples if not m.is_target and getattr(m, pe_attr)
]
default_multiple = next(
    (
        label
        for label, attribute in charts.MULTIPLES.items()
        if any(getattr(m, attribute) for m in snapshot.multiples)
    ),
    "Forward P/E",
)
annual = snapshot.annual
latest = annual[-1] if annual else None
previous = annual[-2] if len(annual) > 1 else None

price_series = [close for _, close in snapshot.price_history.get(snapshot.symbol, [])][-52:]

with st.container():
    row_one = st.columns(3, border=True)
    row_two = st.columns(3, border=True)

with row_one[0]:
    st.metric(
        "Last price",
        number(snapshot.last_price, 2),
        delta=pct(own_year["Return"].iloc[0], signed=True) if not own_year.empty else None,
        delta_description="over 52 weeks" if not own_year.empty else None,
        chart_data=price_series or None,
        chart_type="line",
        height="stretch",
    )
with row_one[1]:
    st.metric(
        "Base intrinsic value",
        number(base.intrinsic_price, 2) if base else "N/A",
        delta=pct(base.margin_of_safety, signed=True) if base else None,
        delta_description="vs market price" if base else None,
        help=(
            f"Bear {bear.intrinsic_price:,.2f} / Base {base.intrinsic_price:,.2f} / "
            f"Bull {bull.intrinsic_price:,.2f}"
            if base and bear and bull
            else "DCF from latest free cash flow."
        ),
        height="stretch",
    )
with row_one[2]:
    st.metric(
        "Margin of safety (base)",
        pct(base.margin_of_safety, signed=True) if base else "N/A",
        help=(
            f"Bear {pct(bear.margin_of_safety, signed=True)} / "
            f"Bull {pct(bull.margin_of_safety, signed=True)}"
            if bear and bull
            else "Base intrinsic value versus market price."
        ),
        height="stretch",
    )
with row_two[0]:
    own_forward = getattr(target_multiple, pe_attr) if target_multiple else None
    peer_median_forward = median(peer_forward) if peer_forward else None
    premium = own_forward / peer_median_forward - 1 if own_forward and peer_median_forward else None
    st.metric(
        pe_label,
        number(own_forward),
        delta=pct(premium, signed=True) if premium is not None else None,
        delta_color="inverse",
        delta_description=(
            f"vs peer median {peer_median_forward:.1f}" if peer_median_forward else None
        ),
        height="stretch",
    )
with row_two[1]:
    fcf_change = (
        latest.free_cash_flow / previous.free_cash_flow - 1
        if latest and previous and latest.free_cash_flow and previous.free_cash_flow
        else None
    )
    st.metric(
        "Free cash flow",
        money(latest.free_cash_flow) if latest else "N/A",
        delta=pct(fcf_change, signed=True) if fcf_change is not None else None,
        delta_description="vs prior year" if fcf_change is not None else None,
        chart_data=[p.free_cash_flow / 1e9 for p in annual if p.free_cash_flow is not None] or None,
        chart_type="bar",
        height="stretch",
    )
with row_two[2]:
    growth = (
        latest.revenue / previous.revenue - 1
        if latest and previous and latest.revenue and previous.revenue
        else None
    )
    st.metric(
        "Revenue growth (YoY)",
        pct(growth, signed=True) if growth is not None else "N/A",
        chart_data=[p.revenue / 1e9 for p in annual if p.revenue is not None] or None,
        chart_type="area",
        height="stretch",
    )

# ---- What stands out -------------------------------------------------------

insights = derive_insights(snapshot)
with st.container(border=True):
    st.subheader("What stands out")
    if insights:
        for insight in insights:
            st.markdown(
                f"{SEVERITY_ICON[insight.severity]} **{insight.title}.** {insight.detail}"
            )
    else:
        st.caption("Not enough data to flag anything yet.")

# ---- Price and momentum ----------------------------------------------------

with st.container(border=True):
    st.subheader("Price versus peers")
    window = st.segmented_control(
        "Window",
        list(charts.RANGE_WEEKS),
        default="1Y",
        required=True,
        key="price_window",
    )
    weeks = charts.RANGE_WEEKS[window]
    price_frame = charts.price_frame(snapshot, weeks)
    if price_frame.empty:
        st.caption("Price history is not available.")
    else:
        st.altair_chart(
            charts.price_chart(price_frame, snapshot.symbol),
            alt=f"Indexed price of {snapshot.symbol} and peers over {window}, rebased to 100",
        )
        stats = charts.price_stats_frame(snapshot, weeks)
        st.dataframe(
            stats,
            hide_index=True,
            column_config={
                "Return": st.column_config.NumberColumn(format="percent"),
                "Volatility (ann.)": st.column_config.NumberColumn(format="percent"),
                "Max drawdown": st.column_config.NumberColumn(format="percent"),
                "vs 52w high": st.column_config.NumberColumn(format="percent"),
            },
            alt=f"Return, volatility, drawdown, and distance from the 52-week high over {window}",
        )

# ---- Fundamentals ----------------------------------------------------------

left, right = st.columns(2)
with left, st.container(border=True):
    st.subheader("Revenue, operating income, free cash flow")
    frame = charts.growth_frame(snapshot)
    if frame.empty:
        st.caption("Financial statements are not available.")
    else:
        st.altair_chart(
            charts.grouped_bar_chart(frame, "Year", "USD bn", "Measure"),
            alt="Annual revenue, operating income, and free cash flow in USD billions",
        )
with right, st.container(border=True):
    st.subheader("Margin trend")
    frame = charts.margin_frame(snapshot)
    if frame.empty:
        st.caption("Margin history is not available.")
    else:
        st.altair_chart(
            charts.margin_chart(frame),
            alt="Gross, operating, and net margin by fiscal year",
        )

# ---- Quality and valuation -------------------------------------------------

left, right = st.columns(2)
with left, st.container(border=True):
    st.subheader("Earnings quality")
    st.caption("Net income against free cash flow. Cash that trails profit is a warning sign.")
    frame = charts.earnings_quality_frame(snapshot)
    if frame.empty:
        st.caption("Earnings quality data is not available.")
    else:
        st.altair_chart(
            charts.grouped_bar_chart(frame, "Year", "USD bn", "Measure"),
            alt="Net income versus free cash flow by fiscal year in USD billions",
        )
with right, st.container(border=True):
    st.subheader("Intrinsic value scenarios")
    st.caption("Dashed line is the market price. Green bars are worth more than the price.")
    valuation = charts.valuation_chart(snapshot)
    if valuation is None:
        st.caption("A DCF needs positive free cash flow and share count data.")
    else:
        st.altair_chart(
            valuation,
            alt="Bear, base, and bull DCF intrinsic value per share against the market price",
        )
        if base:
            st.caption(
                f"Base: growth {pct(base.growth_rate)}, discount rate {pct(base.discount_rate)}, "
                f"terminal growth {pct(base.terminal_growth_rate)}, {base.forecast_years} years."
            )

# ---- Peers and committee ---------------------------------------------------

left, right = st.columns(2)
with left, st.container(border=True):
    st.subheader("Peer multiples")
    metric = st.segmented_control(
        "Multiple",
        list(charts.MULTIPLES),
        default=default_multiple,
        required=True,
        key="multiple_metric",
    )
    frame = charts.multiples_frame(snapshot, metric)
    if frame.empty:
        st.caption(f"{metric} is not available for these tickers.")
    else:
        st.altair_chart(
            charts.multiples_chart(frame, metric),
            alt=f"{metric} for {snapshot.symbol} and peers, with the peer median as a dashed line",
        )
with right, st.container(border=True):
    st.subheader("Committee scores")
    run = get_committee_run()
    if run and run.symbol == snapshot.symbol and run.scores and run.scores.as_rows():
        if run.scores.rating:
            st.badge(run.scores.rating, icon=":material/gavel:", color="blue")
        st.altair_chart(
            charts.scores_chart(run.scores),
            alt="Committee scores out of 10 for fundamental, sentiment, risk, valuation, and final",
        )
        st.caption("Risk is scored so that a higher number means safer.")
    else:
        st.info(
            "Run the committee on the Committee page to add analyst scores here.",
            icon=":material/groups:",
        )
