from __future__ import annotations

import streamlit as st

from src.ui.session import active_ticker, get_context, init_state, set_ticker

st.set_page_config(
    page_title="Investment Committee Terminal",
    page_icon=":material/monitoring:",
    layout="wide",
)

init_state()

try:
    ctx = get_context()
except Exception as exc:  # noqa: BLE001
    st.error(f"Startup failed: {exc}")
    st.info("Configure `.env` using `.env.example` and restart the app.")
    st.stop()

with st.sidebar:
    st.subheader("Research target")
    with st.form("ticker_form", border=False):
        symbol_input = st.text_input("Stock ticker", value=st.session_state["symbol"])
        peers_input = st.text_input(
            "Peers (comma-separated, up to 4)", value=st.session_state["peers"]
        )
        submitted = st.form_submit_button(
            "Analyze", type="primary", icon=":material/search:", width="stretch"
        )
    if submitted:
        if symbol_input.strip():
            set_ticker(symbol_input, peers_input)
            st.rerun()
        else:
            st.warning("Enter a ticker symbol.")

    if st.button(
        "Clear cache and reload",
        icon=":material/refresh:",
        width="stretch",
        help="Drops cached vendor data and rebuilds the dashboard on the next view.",
    ):
        ctx.cache.clear()
        st.session_state.pop("snapshot", None)
        st.rerun()

    with st.expander("Configuration"):
        for name, ok in ctx.settings.api_key_status().items():
            icon = ":material/check_circle:" if ok else ":material/warning:"
            st.write(f"{icon} {name}")

    with st.expander("Cache"):
        st.dataframe(
            ctx.cache.entries(),
            width="stretch",
            hide_index=True,
            alt="Entries currently held in the in-memory data cache",
        )

page = st.navigation(
    [
        st.Page(
            "app_pages/dashboard.py",
            title="Dashboard",
            icon=":material/monitoring:",
            default=True,
        ),
        st.Page(
            "app_pages/committee.py",
            title="Committee",
            icon=":material/groups:",
        ),
        st.Page("app_pages/chat.py", title="Chat", icon=":material/chat:"),
    ],
    position="top",
)

symbol, peers = active_ticker()
st.title(page.title, icon=page.icon)
st.caption(
    f"Target **{symbol}**"
    + (f" against peers {peers.replace(',', ', ')}" if peers else "")
    + ". Research only, not investment advice."
)

page.run()
