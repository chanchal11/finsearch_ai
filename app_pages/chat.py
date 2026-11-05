from __future__ import annotations

import streamlit as st

from src.domain.snapshot import ResearchSnapshot
from src.services.chat_service import build_chat_context
from src.services.research_service import snapshot_summary
from src.ui.session import chat_store, get_committee_run, get_context, get_snapshot
from src.ui.stream_bridge import run_stream

SUGGESTIONS = [
    "Why is the margin of safety what it is?",
    "Is earnings quality deteriorating?",
    "How does valuation compare with peers?",
    "What are the biggest risks right now?",
    "What would have to change to upgrade this?",
]


def _queue_prompt(text: str) -> None:
    st.session_state["queued_prompt"] = text


def _reset_chat(store, session_id: str) -> None:
    store.clear(session_id)
    st.session_state.pop("chat_agent", None)


ctx = get_context()
store, session_id = chat_store()
snapshot: ResearchSnapshot | None = get_snapshot(ctx)

if snapshot is None:
    st.info("Enter a ticker in the sidebar and select Analyze.")
    st.stop()

run = get_committee_run()
report = run.report if run and run.symbol == snapshot.symbol else None

with st.container(horizontal=True, vertical_alignment="center"):
    st.badge(snapshot.symbol, color="gray")
    st.badge(
        "Committee report loaded" if report else "No committee report yet",
        icon=":material/groups:",
        color="green" if report else "gray",
    )
    st.button(
        "Clear conversation",
        icon=":material/delete:",
        on_click=_reset_chat,
        args=(store, session_id),
        disabled=not store.load(session_id),
    )

history = store.load(session_id)
if not history:
    st.caption("Ask about the numbers on the dashboard, the committee report, or the latest news.")
    with st.container(horizontal=True):
        for suggestion in SUGGESTIONS:
            st.button(
                suggestion,
                key=f"suggest_{suggestion}",
                on_click=_queue_prompt,
                args=(suggestion,),
                icon=":material/arrow_outward:",
            )

for message in history:
    with st.chat_message(message.role):
        st.markdown(message.content)
        if message.tools:
            st.caption("Used: " + ", ".join(f"`{name}`" for name in dict.fromkeys(message.tools)))

prompt = st.chat_input(
    f"Ask about {snapshot.symbol}",
    submit_mode="disable",
) or st.session_state.pop("queued_prompt", None)

if prompt:
    context = build_chat_context(snapshot_summary(snapshot), report)
    if "chat_agent" not in st.session_state:
        st.session_state["chat_agent"] = ctx.chat.create_agent(context)
    agent = st.session_state["chat_agent"]

    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        tools_box = st.container()
        answer_slot = st.empty()
        status = None
        answer = ""
        try:
            for event in run_stream(
                lambda: ctx.chat.stream_reply(agent, store, session_id, prompt, context)
            ):
                if event.type == "tool_start":
                    if status is None:
                        with tools_box:
                            status = st.status(":shimmer[Researching]", type="compact")
                    with status:
                        st.write(f":material/build: `{event.data}`")
                elif event.type == "token":
                    answer += event.data
                    answer_slot.markdown(answer + " ▌")
            failed = False
        except Exception as exc:  # noqa: BLE001
            failed = True
            st.error(f"The assistant could not finish: {exc}")
        if status is not None:
            status.update(label="Research steps", state="complete")
    if not failed:
        # Re-render from the store so suggestions hide and Clear conversation enables.
        st.rerun()
