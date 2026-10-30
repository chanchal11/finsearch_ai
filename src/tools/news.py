from __future__ import annotations

import re

from src.core.interfaces import INewsProvider


BULLISH_TERMS = {
    "beat",
    "surge",
    "soar",
    "growth",
    "upgrade",
    "outperform",
    "record",
    "strong",
    "bullish",
    "rally",
    "profit",
    "expansion",
}
BEARISH_TERMS = {
    "miss",
    "decline",
    "fall",
    "cut",
    "downgrade",
    "underperform",
    "weak",
    "bearish",
    "lawsuit",
    "investigation",
    "recall",
    "bankruptcy",
    "layoff",
}


def search_recent_news(
    provider: INewsProvider, query: str, days: int = 7, max_results: int = 8
) -> str:
    payload = provider.search_news(query=query, days=days, max_results=max_results)
    lines = [f"## News Search — {query}", ""]
    for item in payload.get("results", []):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        snippet = item.get("content", "")[:280]
        lines.append(f"- **{title}** — {snippet} ([source]({url}))")
    if len(lines) == 2:
        lines.append("_No articles found._")
    return "\n".join(lines)


def news_desk(provider: INewsProvider, topic: str) -> str:
    return provider.fetch_desk_brief(topic)


def analyze_sentiment(text: str) -> str:
    tokens = set(re.findall(r"[a-zA-Z']+", text.lower()))
    bull = len(tokens & BULLISH_TERMS)
    bear = len(tokens & BEARISH_TERMS)
    if bull > bear + 1:
        label = "Bullish"
    elif bear > bull + 1:
        label = "Bearish"
    else:
        label = "Neutral"
    return (
        f"## Sentiment\n\n"
        f"**Label:** {label}\n\n"
        f"| Bullish hits | Bearish hits |\n| --- | --- |\n| {bull} | {bear} |"
    )
