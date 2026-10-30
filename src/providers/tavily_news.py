from __future__ import annotations

from tavily import TavilyClient

from src.core.interfaces import INewsDataProvider


class TavilyNewsError(RuntimeError):
    pass


class TavilyNewsProvider(INewsDataProvider):
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise TavilyNewsError("TAVILY_API_KEY is required.")
        self._client = TavilyClient(api_key=api_key)

    def search_news(self, query: str, days: int, max_results: int) -> dict:
        try:
            return self._client.search(
                query=query,
                topic="news",
                days=days,
                max_results=max_results,
                include_answer=False,
            )
        except Exception as exc:  # noqa: BLE001 — surface vendor failures to agents
            raise TavilyNewsError(f"Tavily search failed: {exc}") from exc

    def fetch_desk_brief(self, topic: str) -> str:
        try:
            response = self._client.search(
                query=f"Latest market-moving headlines and catalysts for {topic}",
                topic="news",
                days=7,
                max_results=8,
                include_answer=True,
            )
        except Exception as exc:  # noqa: BLE001
            raise TavilyNewsError(f"Tavily desk brief failed: {exc}") from exc
        answer = response.get("answer") or ""
        snippets = []
        for item in response.get("results", [])[:8]:
            title = item.get("title", "Untitled")
            url = item.get("url", "")
            snippets.append(f"- **{title}** ({url})")
        body = "\n".join(snippets) if snippets else "_No headlines returned._"
        return f"### Desk Brief: {topic}\n\n{answer}\n\n{body}"
