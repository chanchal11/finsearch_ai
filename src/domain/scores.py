from __future__ import annotations

import json
import re

from src.domain.snapshot import CommitteeScores

_RATINGS = ("STRONG BUY", "STRONG SELL", "BUY", "HOLD", "SELL")
_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_TABLE_ROW = re.compile(
    r"^\|\s*\**(Fundamental|Sentiment|Risk|Valuation|Final Rating|Final)\**\s*\|\s*\**([^|]*?)\**\s*\|",
    re.IGNORECASE | re.MULTILINE,
)
_SCORE_NUMBER = re.compile(r"(\d+(?:\.\d+)?)")

SCORE_BLOCK_INSTRUCTION = (
    "After PART 2, finish with one machine-readable block exactly in this shape "
    "(integers or decimals from 1 to 10, rating from the allowed list):\n"
    "```json\n"
    '{"scores": {"fundamental": 7, "sentiment": 6, "risk": 5, "valuation": 6, "final": 6}, '
    '"rating": "HOLD"}\n'
    "```"
)


def _clamp(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number < 1 or number > 10:
        return None
    return number


def _normalise_rating(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    upper = value.upper()
    for rating in _RATINGS:
        if rating in upper:
            return rating
    return None


def _from_json(text: str) -> CommitteeScores | None:
    for match in reversed(_JSON_BLOCK.findall(text)):
        try:
            payload = json.loads(match)
        except json.JSONDecodeError:
            continue
        raw = payload.get("scores") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            continue
        scores = CommitteeScores(
            fundamental=_clamp(raw.get("fundamental")),
            sentiment=_clamp(raw.get("sentiment")),
            risk=_clamp(raw.get("risk")),
            valuation=_clamp(raw.get("valuation")),
            final=_clamp(raw.get("final")),
            rating=_normalise_rating(payload.get("rating")),
        )
        if scores.as_rows():
            return scores
    return None


def _from_table(text: str) -> CommitteeScores | None:
    scores = CommitteeScores()
    for label, cell in _TABLE_ROW.findall(text):
        key = label.lower()
        number = _SCORE_NUMBER.search(cell)
        if key == "final rating":
            scores.rating = _normalise_rating(cell) or scores.rating
            continue
        if not number:
            continue
        value = _clamp(number.group(1))
        if key == "final":
            scores.final = value
        else:
            setattr(scores, key, value)
    return scores if scores.as_rows() else None


def parse_committee_scores(report: str) -> CommitteeScores | None:
    """Read scores from the JSON block, falling back to the Part 1 rating table."""
    parsed = _from_json(report) or _from_table(report)
    if parsed is None:
        return None
    if parsed.rating is None:
        for match in re.finditer(r"Final Rating[^\n]*", report, re.IGNORECASE):
            parsed.rating = _normalise_rating(match.group(0)) or parsed.rating
    return parsed


def strip_score_block(report: str) -> str:
    """Remove the machine-readable block so the rendered report stays clean."""

    def _drop(match: re.Match[str]) -> str:
        return "" if '"scores"' in match.group(0) else match.group(0)

    return _JSON_BLOCK.sub(_drop, report).rstrip()
