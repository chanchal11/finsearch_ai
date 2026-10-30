from __future__ import annotations

from strands import Agent

from src.agents.model import build_model
from src.agents.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
from src.agents.specialists import (
    FUNDAMENTAL_SYSTEM_PROMPT,
    NEWS_SYSTEM_PROMPT,
    RISK_SYSTEM_PROMPT,
    VALUATION_SYSTEM_PROMPT,
)
from src.config import Settings
from src.core.cache import ICacheProvider
from src.core.interfaces import IFinancialDataProvider, INewsDataProvider
from src.tools.builder import ToolBundle, build_tool_bundle


def build_orchestrator_agent(
    settings: Settings,
    financial: IFinancialDataProvider,
    news_provider: INewsDataProvider,
    cache: ICacheProvider,
) -> Agent:
    tools: ToolBundle = build_tool_bundle(
        financial,
        news_provider,
        cache,
        cache_ttl=settings.cache_default_ttl,
    )
    model = build_model(settings)

    fundamental = Agent(
        name="fundamental_specialist",
        description=(
            "Deep dive on financial statements, ratios, and capital allocation for a ticker."
        ),
        model=model,
        system_prompt=FUNDAMENTAL_SYSTEM_PROMPT,
        tools=tools.fundamental_tools,
        callback_handler=None,
    )
    news_agent = Agent(
        name="news_sentiment_specialist",
        description="Tracks breaking news, catalysts, and sentiment for a company.",
        model=model,
        system_prompt=NEWS_SYSTEM_PROMPT,
        tools=tools.news_tools,
        callback_handler=None,
    )
    risk = Agent(
        name="risk_specialist",
        description="Bear-case stress test: leverage, liquidity, earnings quality, headline risk.",
        model=model,
        system_prompt=RISK_SYSTEM_PROMPT,
        tools=tools.risk_tools,
        callback_handler=None,
    )
    valuation = Agent(
        name="valuation_specialist",
        description="DCF intrinsic value and peer multiple benchmarking.",
        model=model,
        system_prompt=VALUATION_SYSTEM_PROMPT,
        tools=tools.valuation_tools,
        callback_handler=None,
    )

    orchestrator = Agent(
        name="managing_director",
        description="Investment committee orchestrator producing rating table and executive brief.",
        model=model,
        system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
        tools=[
            fundamental.as_tool(
                name="fundamental_specialist",
                description=fundamental.description,
            ),
            news_agent.as_tool(
                name="news_sentiment_specialist",
                description=news_agent.description,
            ),
            risk.as_tool(name="risk_specialist", description=risk.description),
            valuation.as_tool(
                name="valuation_specialist",
                description=valuation.description,
            ),
        ],
        callback_handler=None,
    )
    return orchestrator
