from __future__ import annotations

import json
from typing import Any

import pandas as pd


def dataframe_to_markdown(df: pd.DataFrame, max_rows: int = 12) -> str:
    if df is None or df.empty:
        return "_No data available._"
    view = df.head(max_rows)
    return view.to_markdown(index=True)


def dict_to_markdown(data: dict[str, Any]) -> str:
    lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str)[:500]
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)
