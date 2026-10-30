from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

from strands import Agent


@dataclass
class StreamEvent:
    type: str
    data: str


class InvestmentCommitteeService:
    """Framework-agnostic orchestration facade for Streamlit and FastAPI."""

    def __init__(self, orchestrator_agent: Agent) -> None:
        self.agent = orchestrator_agent

    def _build_prompt(self, symbol: str, peers: str) -> str:
        symbol = symbol.upper().strip()
        peer_text = peers.strip() or "none supplied"
        return (
            f"Run a full investment committee evaluation on {symbol}. "
            f"Peer set for relative valuation: {peer_text}. "
            "Call each specialist, reconcile disagreements, and produce Part 1 and Part 2."
        )

    def evaluate(self, symbol: str, peers: str = "") -> tuple[str, dict[str, Any]]:
        started = time.perf_counter()
        prompt = self._build_prompt(symbol, peers)
        result = self.agent(prompt)
        elapsed = time.perf_counter() - started
        metrics = {
            "elapsed_seconds": round(elapsed, 3),
            "tool_calls": len(getattr(result.metrics, "tool_metrics", []) or []),
        }
        return str(result), metrics

    async def stream_evaluation(
        self, symbol: str, peers: str = ""
    ) -> AsyncIterator[StreamEvent]:
        prompt = self._build_prompt(symbol, peers)
        async for event in self.agent.stream_async(prompt):
            if isinstance(event, dict):
                if event.get("data"):
                    yield StreamEvent(type="token", data=str(event["data"]))
                tool_use = event.get("current_tool_use") or {}
                name = tool_use.get("name")
                if name:
                    yield StreamEvent(type="tool_start", data=name)
            else:
                event_type = type(event).__name__
                if event_type.endswith("ToolResultEvent"):
                    yield StreamEvent(type="tool_end", data=event_type)
