from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from strands import Agent
from strands.types.content import Message

from src.agents.base import ChatAgentFactory
from src.services.chat_store import ChatMessage, IChatStore
from src.services.streaming import StreamEvent, iter_agent_events

MAX_REPORT_CHARS = 6000


def build_chat_context(snapshot_text: str, committee_report: str | None) -> str:
    """Combine the research snapshot and latest committee report into prompt context."""
    parts = [snapshot_text.strip() or "No snapshot loaded."]
    if committee_report:
        report = committee_report.strip()
        if len(report) > MAX_REPORT_CHARS:
            report = report[:MAX_REPORT_CHARS] + "\n...[report truncated]"
        parts.append("Latest committee report:\n" + report)
    else:
        parts.append("The committee has not been run for this ticker yet.")
    return "\n\n".join(parts)


def _to_strands_messages(history: Sequence[ChatMessage]) -> list[Message]:
    return [{"role": m.role, "content": [{"text": m.content}]} for m in history]


class ChatService:
    """Research chat for the dashboard.

    Streamlit keeps one agent and one store per browser session; the API creates a
    short-lived agent per request from the history the client sends.
    """

    def __init__(self, factory: ChatAgentFactory) -> None:
        self._factory = factory

    def create_agent(
        self, context: str = "", history: Sequence[ChatMessage] | None = None
    ) -> Agent:
        return self._factory.create(
            context, _to_strands_messages(history) if history else None
        )

    async def stream_reply(
        self,
        agent: Agent,
        store: IChatStore,
        session_id: str,
        user_text: str,
        context: str,
    ) -> AsyncIterator[StreamEvent]:
        """Stream a reply, recording both messages in the store."""
        agent.system_prompt = self._factory.render_prompt(context)
        store.append(session_id, ChatMessage(role="user", content=user_text))

        answer: list[str] = []
        tools: list[str] = []
        try:
            async for event in iter_agent_events(agent, user_text):
                if event.type == "token":
                    answer.append(event.data)
                elif event.type == "tool_start":
                    tools.append(event.data)
                yield event
        finally:
            text = "".join(answer).strip()
            if text:
                store.append(
                    session_id,
                    ChatMessage(role="assistant", content=text, tools=tools),
                )

    def reply(
        self, history: Sequence[ChatMessage], user_text: str, context: str
    ) -> tuple[str, int]:
        """Stateless reply for API clients. Returns the answer and tool-call count."""
        agent = self.create_agent(context, history)
        result = agent(user_text)
        tool_calls = len(getattr(result.metrics, "tool_metrics", []) or [])
        return str(result), tool_calls
