from __future__ import annotations

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Callable, Iterator

from src.services.streaming import StreamEvent


def run_stream(
    make_stream: Callable[[], AsyncIterator[StreamEvent]],
) -> Iterator[StreamEvent]:
    """Expose an async event stream as a synchronous iterator for Streamlit.

    The whole async generator runs inside one task on a worker thread. Stepping it
    with a fresh ``run_until_complete`` per chunk copies the context each time, and
    OpenTelemetry then fails to detach a token created in the previous context.
    """
    events: queue.Queue[StreamEvent | BaseException | None] = queue.Queue()

    async def _produce() -> None:
        try:
            async for event in make_stream():
                events.put(event)
        except Exception as exc:  # noqa: BLE001 - re-raised on the consuming thread
            events.put(exc)
        finally:
            events.put(None)

    thread = threading.Thread(target=lambda: asyncio.run(_produce()), daemon=True)
    thread.start()
    try:
        while True:
            item = events.get()
            if item is None:
                return
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        thread.join(timeout=1)
