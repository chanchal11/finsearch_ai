"""Canonical data contract shared by every financial-data adapter.

The tools read Alpha Vantage's column names (``fiscalDateEnding``, ``totalRevenue``,
``SharesOutstanding`` ...). Each adapter translates its vendor's payload into this
shape, so tools, agents, and the dashboard never learn which vendor is active.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import pandas as pd

DATE_COLUMN = "fiscalDateEnding"

INCOME_FIELDS: tuple[str, ...] = (
    "totalRevenue",
    "grossProfit",
    "operatingIncome",
    "netIncome",
)
BALANCE_FIELDS: tuple[str, ...] = (
    "totalCurrentAssets",
    "totalCurrentLiabilities",
    "inventory",
    "totalAssets",
    "totalLiabilities",
    "totalShareholderEquity",
    "shortLongTermDebtTotal",
    "longTermDebt",
    "cashAndCashEquivalentsAtCarryingValue",
    "cashAndShortTermInvestments",
)
CASHFLOW_FIELDS: tuple[str, ...] = (
    "operatingCashflow",
    "capitalExpenditures",
)
OVERVIEW_FIELDS: tuple[str, ...] = (
    "Name",
    "Symbol",
    "Exchange",
    "Currency",
    "Sector",
    "Industry",
    "MarketCapitalization",
    "SharesOutstanding",
    "PERatio",
    "ForwardPE",
    "EVToEBITDA",
    "PriceToBookRatio",
    "PriceToSalesRatioTTM",
)

# Source keys per canonical field, tried in order. Vendors rename fields between API
# versions, so each adapter lists every spelling it has seen.
FieldMap = Mapping[str, Sequence[str]]


class FinancialDataError(RuntimeError):
    """Raised when a vendor cannot supply the requested data."""


def clean_number(value: Any) -> Any:
    """Return ``None`` for missing values (None, NaN, infinity, empty text)."""
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def pick(source: Mapping[str, Any], keys: Iterable[str]) -> Any:
    """First usable value among ``keys`` in ``source``, else ``None``."""
    for key in keys:
        if key in source:
            value = clean_number(source[key])
            if value is not None:
                return value
    return None


def map_record(source: Mapping[str, Any], field_map: FieldMap) -> dict[str, Any]:
    return {canonical: pick(source, keys) for canonical, keys in field_map.items()}


def statement_frame(
    records: Iterable[tuple[str, Mapping[str, Any]]],
    field_map: FieldMap,
) -> pd.DataFrame:
    """Build a statement frame (newest first) from ``(period_end_date, raw_record)`` pairs."""
    rows = []
    for period_end, raw in records:
        row: dict[str, Any] = {DATE_COLUMN: str(period_end)[:10]}
        row.update(map_record(raw, field_map))
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=[DATE_COLUMN, *field_map])
    frame = pd.DataFrame(rows)
    return frame.sort_values(DATE_COLUMN, ascending=False).reset_index(drop=True)


def weekly_closes(prices: pd.DataFrame) -> pd.DataFrame:
    """Reduce a ``date``/``close`` frame of any frequency to week-ending closes."""
    frame = prices.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["close"]).sort_values("date")
    weekly = (
        frame.set_index("date")["close"].resample("W-FRI").last().dropna().reset_index()
    )
    return weekly.rename(columns={"index": "date"}).reset_index(drop=True)


def require_rows(frame: pd.DataFrame, context: str) -> pd.DataFrame:
    if frame.empty:
        raise FinancialDataError(f"{context}: no data returned.")
    return frame
