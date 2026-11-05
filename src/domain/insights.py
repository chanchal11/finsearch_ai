from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Literal

from src.domain.snapshot import ResearchSnapshot

Severity = Literal["positive", "info", "warning", "negative"]


@dataclass
class Insight:
    severity: Severity
    title: str
    detail: str


def _pct(value: float) -> str:
    return f"{value:+.1%}"


def derive_insights(snapshot: ResearchSnapshot) -> list[Insight]:
    """Rule-based observations that point a reader at what deserves attention."""
    insights: list[Insight] = []
    insights.extend(_valuation(snapshot))
    insights.extend(_earnings_quality(snapshot))
    insights.extend(_growth_and_margins(snapshot))
    insights.extend(_relative_valuation(snapshot))
    insights.extend(_price_behaviour(snapshot))
    return insights


def _valuation(snapshot: ResearchSnapshot) -> list[Insight]:
    by_label = {s.label: s for s in snapshot.scenarios}
    base, bull, bear = by_label.get("Base"), by_label.get("Bull"), by_label.get("Bear")
    if base is None:
        return []
    if bull is not None and bull.margin_of_safety < 0:
        return [
            Insight(
                "negative",
                "Price is above every DCF scenario",
                f"Even the bull case ({bull.intrinsic_price:,.2f}) sits {_pct(bull.margin_of_safety)} "
                f"versus the market price of {base.market_price:,.2f}.",
            )
        ]
    if base.margin_of_safety >= 0.15:
        return [
            Insight(
                "positive",
                "Base-case DCF shows a margin of safety",
                f"Base intrinsic value {base.intrinsic_price:,.2f} is {_pct(base.margin_of_safety)} "
                f"versus the market price"
                + (
                    f"; the bear case is {_pct(bear.margin_of_safety)}."
                    if bear is not None
                    else "."
                ),
            )
        ]
    if base.margin_of_safety <= -0.15:
        return [
            Insight(
                "warning",
                "Base-case DCF sits below the market price",
                f"Base intrinsic value {base.intrinsic_price:,.2f} is {_pct(base.margin_of_safety)}; "
                "the price needs bull-case growth to be justified.",
            )
        ]
    return [
        Insight(
            "info",
            "Price is close to base-case fair value",
            f"Base intrinsic value {base.intrinsic_price:,.2f} is {_pct(base.margin_of_safety)} "
            "versus the market price.",
        )
    ]


def _earnings_quality(snapshot: ResearchSnapshot) -> list[Insight]:
    points = [p for p in snapshot.annual if p.cash_conversion is not None]
    if not points:
        return []
    latest = points[-1]
    conversion = latest.cash_conversion
    if conversion is None:
        return []
    if conversion < 0.8:
        return [
            Insight(
                "warning",
                "Cash conversion is weak",
                f"{latest.fiscal_year} free cash flow is {conversion:.2f}x net income; "
                "profits are not fully showing up as cash.",
            )
        ]
    if conversion >= 1.0:
        return [
            Insight(
                "positive",
                "Profits are backed by cash",
                f"{latest.fiscal_year} free cash flow is {conversion:.2f}x net income.",
            )
        ]
    return []


def _growth_and_margins(snapshot: ResearchSnapshot) -> list[Insight]:
    insights: list[Insight] = []
    points = snapshot.annual
    if len(points) < 2:
        return insights

    first, last = points[0], points[-1]
    years = len(points) - 1
    if first.revenue and last.revenue and first.revenue > 0 and last.revenue > 0:
        cagr = (last.revenue / first.revenue) ** (1 / years) - 1
        if cagr >= 0.10:
            insights.append(
                Insight(
                    "positive",
                    "Revenue is compounding quickly",
                    f"Revenue CAGR is {cagr:.1%} from {first.fiscal_year} to {last.fiscal_year}.",
                )
            )
        elif cagr < 0:
            insights.append(
                Insight(
                    "negative",
                    "Revenue is shrinking",
                    f"Revenue CAGR is {cagr:.1%} from {first.fiscal_year} to {last.fiscal_year}.",
                )
            )

    if first.operating_margin is not None and last.operating_margin is not None:
        change = last.operating_margin - first.operating_margin
        if change <= -0.02:
            insights.append(
                Insight(
                    "warning",
                    "Operating margin is compressing",
                    f"Down {abs(change) * 100:.1f} points to {last.operating_margin:.1%} "
                    f"since {first.fiscal_year}.",
                )
            )
        elif change >= 0.02:
            insights.append(
                Insight(
                    "positive",
                    "Operating margin is expanding",
                    f"Up {change * 100:.1f} points to {last.operating_margin:.1%} "
                    f"since {first.fiscal_year}.",
                )
            )
    return insights


def _relative_valuation(snapshot: ResearchSnapshot) -> list[Insight]:
    target = next((m for m in snapshot.multiples if m.is_target), None)
    peers = [m for m in snapshot.multiples if not m.is_target]
    if target is None or not peers:
        return []
    for label, attribute in (("forward P/E", "forward_pe"), ("EV/EBITDA", "ev_ebitda")):
        own = getattr(target, attribute)
        peer_values = [getattr(m, attribute) for m in peers if getattr(m, attribute)]
        if not own or not peer_values:
            continue
        peer_median = median(peer_values)
        premium = own / peer_median - 1
        if premium >= 0.25:
            return [
                Insight(
                    "warning",
                    "Trades at a premium to peers",
                    f"{snapshot.symbol} {label} of {own:.1f} is {premium:.0%} above the "
                    f"peer median of {peer_median:.1f}.",
                )
            ]
        if premium <= -0.15:
            return [
                Insight(
                    "positive",
                    "Trades at a discount to peers",
                    f"{snapshot.symbol} {label} of {own:.1f} is {abs(premium):.0%} below the "
                    f"peer median of {peer_median:.1f}.",
                )
            ]
        return [
            Insight(
                "info",
                "Valued in line with peers",
                f"{snapshot.symbol} {label} of {own:.1f} versus a peer median of {peer_median:.1f}.",
            )
        ]
    return []


def _price_behaviour(snapshot: ResearchSnapshot) -> list[Insight]:
    insights: list[Insight] = []
    own = next((s for s in snapshot.price_stats if s.symbol == snapshot.symbol), None)
    if own is None:
        return insights

    if own.max_drawdown <= -0.30:
        insights.append(
            Insight(
                "warning",
                "Deep drawdown in the window",
                f"Peak-to-trough decline of {own.max_drawdown:.0%} over {own.weeks} weeks.",
            )
        )
    if own.pct_from_52w_high is not None and own.pct_from_52w_high >= -0.03:
        insights.append(
            Insight(
                "info",
                "Trading near its 52-week high",
                f"Price is {own.pct_from_52w_high:.1%} from the high; entry timing matters.",
            )
        )

    peer_returns = [s.total_return for s in snapshot.price_stats if s.symbol != snapshot.symbol]
    if peer_returns:
        gap = own.total_return - median(peer_returns)
        if gap >= 0.10:
            insights.append(
                Insight(
                    "info",
                    "Outperforming peers",
                    f"{own.weeks}-week return is {gap * 100:.0f} points ahead of the peer median.",
                )
            )
        elif gap <= -0.10:
            insights.append(
                Insight(
                    "warning",
                    "Lagging peers",
                    f"{own.weeks}-week return is {abs(gap) * 100:.0f} points behind the peer median.",
                )
            )
    return insights
