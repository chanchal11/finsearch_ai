from __future__ import annotations

from dataclasses import dataclass

from src.agents.base import ChatAgentFactory, build_orchestrator_agent
from src.config import Settings, get_settings
from src.core.cache import InMemoryTTLCache
from src.providers.alpha_vantage import AlphaVantageProvider
from src.providers.cached import CachedFinancialProvider
from src.providers.tavily_news import TavilyNewsProvider
from src.services.chat_service import ChatService
from src.services.committee_service import InvestmentCommitteeService
from src.services.research_service import ResearchService
from src.tools.builder import build_tool_bundle


@dataclass
class AppContext:
    settings: Settings
    cache: InMemoryTTLCache
    service: InvestmentCommitteeService
    research: ResearchService
    chat: ChatService


def build_context(settings: Settings | None = None) -> AppContext:
    settings = settings or get_settings()
    cache = InMemoryTTLCache(
        maxsize=settings.cache_max_size,
        default_ttl=settings.cache_default_ttl,
    )
    financial = CachedFinancialProvider(
        AlphaVantageProvider(settings.alpha_vantage_api_key),
        cache,
        ttl=settings.cache_default_ttl,
    )
    news = TavilyNewsProvider(settings.tavily_api_key)
    tools = build_tool_bundle(
        financial, news, cache, cache_ttl=settings.cache_default_ttl
    )
    return AppContext(
        settings=settings,
        cache=cache,
        service=InvestmentCommitteeService(build_orchestrator_agent(settings, tools)),
        research=ResearchService(financial),
        chat=ChatService(ChatAgentFactory(settings, tools)),
    )
