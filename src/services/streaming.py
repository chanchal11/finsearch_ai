from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from strands import Agent


@dataclass
class StreamEvent:
    type: str
    data: str


async def iter_agent_events(agent: Agent, prompt: str) -> AsyncIterator[StreamEvent]:
    """Translate Strands stream events into token and tool events.

    Strands repeats ``current_tool_use`` on every delta while a tool call is being
    assembled, so each tool call is announced once, keyed by its ``toolUseId``.
    """
    announced: set[str] = set()
    async for event in agent.stream_async(prompt):
        if isinstance(event, dict):
            if event.get("data"):
                yield StreamEvent(type="token", data=str(event["data"]))
            tool_use = event.get("current_tool_use") or {}
            name = tool_use.get("name")
            if name:
                call_id = str(tool_use.get("toolUseId") or name)
                if call_id not in announced:
                    announced.add(call_id)
                    yield StreamEvent(type="tool_start", data=name)
        else:
            event_type = type(event).__name__
            if event_type.endswith("ToolResultEvent"):
                yield StreamEvent(type="tool_end", data=event_type)
