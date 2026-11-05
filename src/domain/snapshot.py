from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AnnualPoint:
    """One fiscal year of income statement and cash flow data."""

    fiscal_year: str
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None

    @property
    def gross_margin(self) -> float | None:
        return _ratio(self.gross_profit, self.revenue)

    @property
    def operating_margin(self) -> float | None:
        return _ratio(self.operating_income, self.revenue)

    @property
    def net_margin(self) -> float | None:
        return _ratio(self.net_income, self.revenue)

    @property
    def cash_conversion(self) -> float | None:
        """Free cash flow divided by net income (earnings quality)."""
        return _ratio(self.free_cash_flow, self.net_income)


@dataclass
class DcfResult:
    symbol: str
    label: str
    base_fcf: float
    net_debt: float
    enterprise_value: float
    equity_value: float
    shares_outstanding: float
    intrinsic_price: float
    market_price: float
    margin_of_safety: float
    growth_rate: float
    discount_rate: float
    terminal_growth_rate: float
    forecast_years: int
    projection: list[dict[str, float]] = field(default_factory=list)


@dataclass
class PeerMultiple:
    symbol: str
    is_target: bool = False
    pe: float | None = None
    forward_pe: float | None = None
    ev_ebitda: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    market_cap: float | None = None


@dataclass
class PriceStats:
    symbol: str
    last_price: float
    total_return: float
    annualized_volatility: float | None
    max_drawdown: float
    high_52w: float | None
    low_52w: float | None
    pct_from_52w_high: float | None
    weeks: int


@dataclass
class CommitteeScores:
    """Scores (1-10) parsed from the Managing Director's report."""

    fundamental: float | None = None
    sentiment: float | None = None
    risk: float | None = None
    valuation: float | None = None
    final: float | None = None
    rating: str | None = None

    def as_rows(self) -> list[dict[str, Any]]:
        labels = (
            ("Fundamental", self.fundamental),
            ("Sentiment", self.sentiment),
            ("Risk", self.risk),
            ("Valuation", self.valuation),
            ("Final", self.final),
        )
        return [{"dimension": name, "score": value} for name, value in labels if value is not None]


@dataclass
class ResearchSnapshot:
    """Deterministic, model-free research data used by the dashboard and chat."""

    symbol: str
    peers: list[str]
    name: str = ""
    sector: str = ""
    industry: str = ""
    currency: str = "USD"
    last_price: float | None = None
    annual: list[AnnualPoint] = field(default_factory=list)
    multiples: list[PeerMultiple] = field(default_factory=list)
    scenarios: list[DcfResult] = field(default_factory=list)
    price_history: dict[str, list[tuple[str, float]]] = field(default_factory=dict)
    price_stats: list[PriceStats] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def base_scenario(self) -> DcfResult | None:
        for scenario in self.scenarios:
            if scenario.label == "Base":
                return scenario
        return self.scenarios[0] if self.scenarios else None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for point_dict, point in zip(data["annual"], self.annual, strict=True):
            point_dict["gross_margin"] = point.gross_margin
            point_dict["operating_margin"] = point.operating_margin
            point_dict["net_margin"] = point.net_margin
            point_dict["cash_conversion"] = point.cash_conversion
        return _json_safe(data)


def _json_safe(value: Any) -> Any:
    """Replace NaN and infinity (invalid in JSON) with None, recursively."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator
