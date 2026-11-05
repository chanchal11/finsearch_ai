from __future__ import annotations

import logging
from collections.abc import Callable

from src.core.interfaces import IFinancialDataProvider
from src.domain.snapshot import ResearchSnapshot
from src.tools import fundamentals, market, valuation

logger = logging.getLogger(__name__)

MAX_PEERS = 4
HISTORY_WEEKS = 104


def parse_tickers(raw: str) -> list[str]:
    seen: dict[str, None] = {}
    for part in raw.replace(";", ",").replace(" ", ",").split(","):
        symbol = part.strip().upper()
        if symbol:
            seen[symbol] = None
    return list(seen)


class ResearchService:
    """Builds the model-free research snapshot behind the dashboard and chat.

    The injected provider is expected to be cached (see ``CachedFinancialProvider``),
    so repeated builds reuse vendor responses and stay inside API rate limits.
    """

    def __init__(self, financial: IFinancialDataProvider) -> None:
        self._financial = financial

    def build_snapshot(self, symbol: str, peers: str = "") -> ResearchSnapshot:
        symbol = symbol.upper().strip()
        peer_list = [p for p in parse_tickers(peers) if p != symbol]
        warnings: list[str] = []
        if len(peer_list) > MAX_PEERS:
            warnings.append(
                f"Using the first {MAX_PEERS} peers ({', '.join(peer_list[:MAX_PEERS])}) "
                "to stay within data-provider rate limits."
            )
            peer_list = peer_list[:MAX_PEERS]

        snapshot = ResearchSnapshot(symbol=symbol, peers=peer_list, warnings=warnings)

        self._load_profile(snapshot)
        self._load_annual(snapshot)
        self._load_scenarios(snapshot)
        self._load_multiples(snapshot)
        self._load_prices(snapshot)
        if snapshot.last_price is None and snapshot.price_history.get(symbol):
            snapshot.last_price = snapshot.price_history[symbol][-1][1]
        return snapshot

    def _guard(
        self, snapshot: ResearchSnapshot, section: str, action: Callable[[], None]
    ) -> None:
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - one failed section must not blank the page
            logger.warning("snapshot section %s failed for %s: %s", section, snapshot.symbol, exc)
            snapshot.warnings.append(f"{section}: {exc}")

    def _load_profile(self, snapshot: ResearchSnapshot) -> None:
        def run() -> None:
            overview = self._financial.get_overview(snapshot.symbol)
            snapshot.name = str(overview.get("Name") or snapshot.symbol)
            snapshot.sector = str(overview.get("Sector") or "")
            snapshot.industry = str(overview.get("Industry") or "")
            snapshot.currency = str(overview.get("Currency") or "USD")

        self._guard(snapshot, "Company profile", run)

    def _load_annual(self, snapshot: ResearchSnapshot) -> None:
        def run() -> None:
            snapshot.annual = fundamentals.annual_history(self._financial, snapshot.symbol)

        self._guard(snapshot, "Financial statements", run)

    def _load_scenarios(self, snapshot: ResearchSnapshot) -> None:
        def run() -> None:
            snapshot.scenarios = valuation.dcf_scenarios(self._financial, snapshot.symbol)
            snapshot.last_price = snapshot.scenarios[0].market_price

        self._guard(snapshot, "DCF scenarios", run)

    def _load_multiples(self, snapshot: ResearchSnapshot) -> None:
        def run() -> None:
            snapshot.multiples = valuation.peer_multiples(
                self._financial, snapshot.peers, target=snapshot.symbol
            )

        self._guard(snapshot, "Peer multiples", run)

    def _load_prices(self, snapshot: ResearchSnapshot) -> None:
        for ticker in [snapshot.symbol, *snapshot.peers]:

            def run(ticker: str = ticker) -> None:
                prices = self._financial.get_weekly_prices(ticker)
                recent = prices.sort_values("date").tail(HISTORY_WEEKS + 1)
                snapshot.price_history[ticker] = [
                    (row.date.strftime("%Y-%m-%d"), float(row.close))
                    for row in recent.itertuples()
                ]
                snapshot.price_stats.append(
                    market.compute_price_stats(ticker, recent, HISTORY_WEEKS)
                )

            self._guard(snapshot, f"Price history ({ticker})", run)


def snapshot_summary(snapshot: ResearchSnapshot) -> str:
    """Compact plain-text view of the snapshot used as chat context."""
    lines = [
        f"Ticker: {snapshot.symbol} ({snapshot.name or 'name unavailable'})",
        f"Sector/industry: {snapshot.sector or 'n/a'} / {snapshot.industry or 'n/a'}",
        f"Peers: {', '.join(snapshot.peers) or 'none'}",
    ]
    if snapshot.last_price is not None:
        lines.append(f"Last price: {snapshot.last_price:,.2f} {snapshot.currency}")

    for scenario in snapshot.scenarios:
        lines.append(
            f"DCF {scenario.label}: intrinsic {scenario.intrinsic_price:,.2f}, "
            f"margin of safety {scenario.margin_of_safety:+.1%} "
            f"(growth {scenario.growth_rate:.1%}, discount {scenario.discount_rate:.1%}, "
            f"terminal {scenario.terminal_growth_rate:.1%})"
        )

    if snapshot.annual:
        lines.append("Annual history (oldest to newest):")
        for point in snapshot.annual:

            def pct(value: float | None) -> str:
                return f"{value:.1%}" if value is not None else "n/a"

            def money(value: float | None) -> str:
                return f"{value / 1e9:,.2f}B" if value is not None else "n/a"

            lines.append(
                f"- {point.fiscal_year}: revenue {money(point.revenue)}, "
                f"op margin {pct(point.operating_margin)}, net margin {pct(point.net_margin)}, "
                f"net income {money(point.net_income)}, FCF {money(point.free_cash_flow)}"
            )

    if snapshot.multiples:
        lines.append("Multiples (P/E, forward P/E, EV/EBITDA, P/S):")
        for row in snapshot.multiples:
            tag = " (target)" if row.is_target else ""
            lines.append(
                f"- {row.symbol}{tag}: {row.pe}, {row.forward_pe}, {row.ev_ebitda}, {row.price_to_sales}"
            )

    for stats in snapshot.price_stats:
        lines.append(
            f"Price {stats.symbol}: {stats.weeks}w return {stats.total_return:+.1%}, "
            f"max drawdown {stats.max_drawdown:.1%}"
        )

    if snapshot.warnings:
        lines.append("Data gaps: " + "; ".join(snapshot.warnings))
    return "\n".join(lines)
