from __future__ import annotations

import json
import time

import streamlit as st

from src.domain.scores import parse_committee_scores, strip_score_block
from src.domain.snapshot import CommitteeScores
from src.ui import charts
from src.ui.session import (
    CommitteeRun,
    active_ticker,
    get_committee_run,
    get_context,
)
from src.ui.stream_bridge import run_stream

ctx = get_context()
symbol, peers = active_ticker()

if not symbol:
    st.info("Enter a ticker in the sidebar and select Analyze.")
    st.stop()

st.write(
    "Five specialists (fundamental, news and sentiment, risk, valuation, market) report to "
    "the Managing Director, who writes the rating table and executive brief."
)

run_clicked = st.button(
    f"Run investment committee for {symbol}",
    type="primary",
    icon=":material/play_arrow:",
)

report_slot = st.container()

if run_clicked:
    started = time.perf_counter()
    tools_used: list[str] = []
    text = ""
    scores: CommitteeScores | None = None

    with report_slot:
        status = st.status("Investment committee in session", expanded=True)
        stream_slot = st.empty()
        try:
            for event in run_stream(lambda: ctx.service.stream_evaluation(symbol, peers)):
                if event.type == "tool_start":
                    tools_used.append(event.data)
                    status.write(f":material/build: Specialist or tool invoked: `{event.data}`")
                elif event.type == "token":
                    text += event.data
                    stream_slot.markdown(strip_score_block(text) + " ▌")
                elif event.type == "scores":
                    scores = CommitteeScores(**json.loads(event.data))
        except Exception as exc:  # noqa: BLE001
            status.update(label="Committee run failed", state="error")
            st.error(f"The committee run stopped: {exc}")
            st.stop()
        status.update(label="Committee session complete", state="complete", expanded=False)
        stream_slot.empty()

    st.session_state["committee_run"] = CommitteeRun(
        symbol=symbol,
        peers=peers,
        report=strip_score_block(text),
        scores=scores or parse_committee_scores(text),
        elapsed_seconds=time.perf_counter() - started,
    )
    st.rerun()

run = get_committee_run()
with report_slot:
    if run is None:
        st.info(
            "No committee report yet. Run the committee to get a rating table and executive brief.",
            icon=":material/groups:",
        )
    else:
        if run.symbol != symbol:
            st.warning(
                f"This report is for {run.symbol}, not the current target {symbol}.",
                icon=":material/warning:",
            )
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(run.symbol, color="gray")
            if run.scores and run.scores.rating:
                st.badge(run.scores.rating, icon=":material/gavel:", color="blue")
            st.caption(f"Completed in {run.elapsed_seconds:,.0f}s")

        if run.scores and run.scores.as_rows():
            with st.container(border=True):
                st.subheader("Scores")
                st.altair_chart(
                    charts.scores_chart(run.scores),
                    alt="Committee scores out of 10 for fundamental, sentiment, risk, valuation, and final",
                )
                st.caption("Risk is scored so that a higher number means safer.")
        st.markdown(run.report)
