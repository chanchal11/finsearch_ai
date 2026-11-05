from __future__ import annotations

import uuid
from dataclasses import dataclass

import streamlit as st

from src.bootstrap import AppContext, build_context
from src.domain.snapshot import CommitteeScores, ResearchSnapshot
from src.services.chat_store import IChatStore, InMemoryChatStore
from src.services.research_service import parse_tickers

DEFAULT_SYMBOL = "AAPL"
DEFAULT_PEERS = "MSFT,GOOGL"


@st.cache_resource
def get_context() -> AppContext:
    return build_context()


@dataclass
class CommitteeRun:
    symbol: str
    peers: str
    report: str
    scores: CommitteeScores | None
    elapsed_seconds: float


def init_state() -> None:
    st.session_state.setdefault("symbol", DEFAULT_SYMBOL)
    st.session_state.setdefault("peers", DEFAULT_PEERS)


def set_ticker(symbol: str, peers: str) -> None:
    """Apply new ticker inputs and drop results that belonged to the previous ones."""
    symbol = symbol.upper().strip()
    peer_list = [p for p in parse_tickers(peers) if p != symbol]
    st.session_state["symbol"] = symbol
    st.session_state["peers"] = ",".join(peer_list)
    st.session_state.pop("snapshot", None)


def active_ticker() -> tuple[str, str]:
    return st.session_state["symbol"], st.session_state["peers"]


def get_snapshot(ctx: AppContext, *, refresh: bool = False) -> ResearchSnapshot | None:
    """Return the snapshot for the active ticker, building it once per ticker."""
    symbol, peers = active_ticker()
    if not symbol:
        return None
    cached: ResearchSnapshot | None = st.session_state.get("snapshot")
    if (
        not refresh
        and cached is not None
        and st.session_state.get("snapshot_key") == (symbol, peers)
    ):
        return cached
    with st.spinner(f"Loading research data for {symbol}...", show_time=True):
        snapshot = ctx.research.build_snapshot(symbol, peers)
    st.session_state["snapshot"] = snapshot
    st.session_state["snapshot_key"] = (symbol, peers)
    return snapshot


def get_committee_run() -> CommitteeRun | None:
    return st.session_state.get("committee_run")


def chat_store() -> tuple[IChatStore, str]:
    """Per-browser-session transcript store (swap for a database-backed store later)."""
    if "chat_store" not in st.session_state:
        st.session_state["chat_store"] = InMemoryChatStore()
        st.session_state["chat_session_id"] = uuid.uuid4().hex
    return st.session_state["chat_store"], st.session_state["chat_session_id"]
