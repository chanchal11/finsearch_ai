from __future__ import annotations

from dataclasses import dataclass

from src.agents.base import build_orchestrator_agent
from src.config import Settings, get_settings
from src.core.cache import InMemoryTTLCache
from src.providers.alpha_vantage import AlphaVantageProvider
from src.providers.tavily_news import TavilyNewsProvider
from src.services.committee_service import InvestmentCommitteeService


@dataclass
class AppContext:
    settings: Settings
    cache: InMemoryTTLCache
    service: InvestmentCommitteeService


def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or get_settings()
    cache = InMemoryTTLCache(
        maxsize=settings.cache_max_size,
        default_ttl=settings.cache_default_ttl,
    )
    financial = AlphaVantageProvider(settings.alpha_vantage_api_key)
    news = TavilyNewsProvider(settings.tavily_api_key)
    orchestrator = build_orchestrator_agent(settings, financial, news, cache)
    service = InvestmentCommitteeService(orchestrator)
    return AppContext(settings=settings, cache=cache, service=service)
