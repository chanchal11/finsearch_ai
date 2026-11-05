from __future__ import annotations

from collections.abc import Sequence

from strands import Agent
from strands.types.content import Message

from src.agents.model import build_model
from src.agents.orchestrator import ORCHESTRATOR_SYSTEM_PROMPT
from src.agents.specialists import (
    CHAT_SYSTEM_PROMPT,
    FUNDAMENTAL_SYSTEM_PROMPT,
    MARKET_SYSTEM_PROMPT,
    NEWS_SYSTEM_PROMPT,
    RISK_SYSTEM_PROMPT,
    VALUATION_SYSTEM_PROMPT,
)
from src.config import Settings
from src.tools.builder import ToolBundle


def build_orchestrator_agent(settings: Settings, tools: ToolBundle) -> Agent:
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
        description="Bear-case stress test: leverage, liquidity, earnings quality, headline risk, drawdown.",
        model=model,
        system_prompt=RISK_SYSTEM_PROMPT,
        tools=tools.risk_tools,
        callback_handler=None,
    )
    valuation = Agent(
        name="valuation_specialist",
        description="Bear/base/bull DCF intrinsic value and peer multiple benchmarking.",
        model=model,
        system_prompt=VALUATION_SYSTEM_PROMPT,
        tools=tools.valuation_tools,
        callback_handler=None,
    )
    market = Agent(
        name="market_specialist",
        description="Price trend, relative performance versus peers, volatility, and drawdown.",
        model=model,
        system_prompt=MARKET_SYSTEM_PROMPT,
        tools=tools.market_tools,
        callback_handler=None,
    )

    return Agent(
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
            market.as_tool(
                name="market_specialist",
                description=market.description,
            ),
        ],
        callback_handler=None,
    )


class ChatAgentFactory:
    """Creates independent research-chat agents so no two sessions share a transcript."""

    def __init__(self, settings: Settings, tools: ToolBundle) -> None:
        self._settings = settings
        self._tools = tools
        self._model = build_model(settings)

    @staticmethod
    def render_prompt(context: str) -> str:
        return CHAT_SYSTEM_PROMPT.format(context=context or "No research context loaded yet.")

    def create(
        self, context: str = "", history: Sequence[Message] | None = None
    ) -> Agent:
        return Agent(
            name="research_assistant",
            description="Answers follow-up questions about a company using research tools.",
            model=self._model,
            system_prompt=self.render_prompt(context),
            tools=self._tools.all_tools,
            messages=list(history) if history else None,
            callback_handler=None,
        )
