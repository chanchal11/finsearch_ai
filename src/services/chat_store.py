from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str
    tools: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class IChatStore(ABC):
    """Persistence boundary for chat transcripts.

    A database-backed implementation can replace ``InMemoryChatStore`` without
    touching the chat service or any UI.
    """

    @abstractmethod
    def load(self, session_id: str) -> list[ChatMessage]: ...

    @abstractmethod
    def append(self, session_id: str, message: ChatMessage) -> None: ...

    @abstractmethod
    def clear(self, session_id: str) -> None: ...


class InMemoryChatStore(IChatStore):
    """Process-local transcript store keyed by session id."""

    def __init__(self) -> None:
        self._messages: dict[str, list[ChatMessage]] = {}
        self._lock = threading.Lock()

    def load(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            return list(self._messages.get(session_id, []))

    def append(self, session_id: str, message: ChatMessage) -> None:
        with self._lock:
            self._messages.setdefault(session_id, []).append(message)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._messages.pop(session_id, None)
