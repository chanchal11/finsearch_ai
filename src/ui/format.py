from __future__ import annotations


def money(value: float | None, currency_prefix: str = "$") -> str:
    """Compact currency text such as ``$1.23T``, ``$456.7B``, or ``N/A``."""
    if value is None:
        return "N/A"
    sign = "-" if value < 0 else ""
    magnitude = abs(value)
    for unit, size in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if magnitude >= size:
            return f"{sign}{currency_prefix}{magnitude / size:,.2f}{unit}"
    return f"{sign}{currency_prefix}{magnitude:,.0f}"


def pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    return f"{value:+.1%}" if signed else f"{value:.1%}"


def number(value: float | None, digits: int = 1) -> str:
    return "N/A" if value is None else f"{value:,.{digits}f}"
