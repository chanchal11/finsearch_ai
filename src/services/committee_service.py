from __future__ import annotations

import dataclasses
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from strands import Agent

from src.domain.scores import parse_committee_scores, strip_score_block
from src.services.streaming import StreamEvent, iter_agent_events

__all__ = ["InvestmentCommitteeService", "StreamEvent"]


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

    def _reset_conversation(self) -> None:
        """Start every evaluation fresh so one ticker's run never leaks into the next."""
        self.agent.messages.clear()

    def evaluate(self, symbol: str, peers: str = "") -> tuple[str, dict[str, Any]]:
        self._reset_conversation()
        started = time.perf_counter()
        prompt = self._build_prompt(symbol, peers)
        result = self.agent(prompt)
        elapsed = time.perf_counter() - started
        raw = str(result)
        scores = parse_committee_scores(raw)
        metrics: dict[str, Any] = {
            "elapsed_seconds": round(elapsed, 3),
            "tool_calls": len(getattr(result.metrics, "tool_metrics", []) or []),
            "scores": dataclasses.asdict(scores) if scores else None,
        }
        return strip_score_block(raw), metrics

    async def stream_evaluation(
        self, symbol: str, peers: str = ""
    ) -> AsyncIterator[StreamEvent]:
        """Stream tokens and tool events, then a final ``scores`` event (JSON) when parsed."""
        self._reset_conversation()
        prompt = self._build_prompt(symbol, peers)
        report_parts: list[str] = []
        async for event in iter_agent_events(self.agent, prompt):
            if event.type == "token":
                report_parts.append(event.data)
            yield event

        scores = parse_committee_scores("".join(report_parts))
        if scores:
            yield StreamEvent(type="scores", data=json.dumps(dataclasses.asdict(scores)))
