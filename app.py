from __future__ import annotations

import asyncio
import queue
import threading

import streamlit as st

from src.bootstrap import AppContext, build_context
from src.services.committee_service import StreamEvent


@st.cache_resource
def get_context() -> AppContext:
    return build_context()


def _stream_tokens(symbol: str, peers: str):
    """Bridge the async agent stream into Streamlit's sync generator.

    The whole async generator must run inside one task. Stepping it with a
    fresh ``run_until_complete`` per chunk copies the context each time, and
    OpenTelemetry then fails to detach a token created in the previous context.
    """
    ctx = get_context()
    events: queue.Queue[StreamEvent | BaseException | None] = queue.Queue()

    async def _produce() -> None:
        try:
            async for event in ctx.service.stream_evaluation(symbol, peers):
                events.put(event)
        except Exception as exc:
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
            if item.type == "token":
                yield item.data
            elif item.type == "tool_start":
                st.session_state.setdefault("tool_log", []).append(
                    f"Specialist/tool invoked: **{item.data}**"
                )
    finally:
        thread.join(timeout=1)


def main() -> None:
    st.set_page_config(
        page_title="Investment Committee Terminal",
        page_icon="📊",
        layout="wide",
    )
    st.title("Investment Committee Terminal")
    st.caption("Multi-agent research engine powered by Strands, Alpha Vantage, and Tavily.")

    try:
        ctx = get_context()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Startup failed: {exc}")
        st.info("Configure `.env` using `.env.example` and restart the app.")
        return

    with st.sidebar:
        st.subheader("Configuration")
        for name, ok in ctx.settings.api_key_status().items():
            st.write(f"{'✅' if ok else '⚠️'} {name}")

        st.subheader("Cache")
        entries = ctx.cache.entries()
        st.dataframe(entries, width="stretch", hide_index=True)
        if st.button("Clear Cache", type="secondary"):
            ctx.cache.clear()
            st.success("Cache cleared.")
            st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        symbol = st.text_input("Stock ticker", value="AAPL").upper().strip()
    with col2:
        peers = st.text_input("Peers (comma-separated)", value="MSFT,GOOGL")

    run = st.button("Run Investment Committee", type="primary")

    if run:
        if not symbol:
            st.warning("Enter a ticker symbol.")
            return

        st.session_state["tool_log"] = []
        with st.status("Investment Committee in Session...", expanded=True) as status:
            for line in st.session_state.get("tool_log", []):
                st.markdown(line)
            streamed = st.write_stream(_stream_tokens(symbol, peers))
            status.update(label="Committee session complete", state="complete")

        with st.expander("Final Report", expanded=True):
            st.markdown(streamed)


if __name__ == "__main__":
    main()
