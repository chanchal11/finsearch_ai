from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from src.bootstrap import AppContext, build_context

app = FastAPI(
    title="Investment Committee API",
    version="0.1.0",
    description="Headless REST + SSE access to the multi-agent investment engine.",
)

_context: AppContext | None = None


@app.on_event("startup")
def _startup() -> None:
    global _context
    _context = build_context()


def get_ctx() -> AppContext:
    if _context is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return _context


class EvaluateRequest(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)
    peers: str = ""


class EvaluateResponse(BaseModel):
    symbol: str
    peers: str
    report_markdown: str
    metrics: dict[str, Any]


@app.post("/api/v1/evaluate", response_model=EvaluateResponse)
def evaluate(payload: EvaluateRequest) -> EvaluateResponse:
    ctx = get_ctx()
    symbol = payload.symbol.upper().strip()
    try:
        report, metrics = ctx.service.evaluate(symbol, payload.peers)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return EvaluateResponse(
        symbol=symbol,
        peers=payload.peers,
        report_markdown=report,
        metrics=metrics,
    )


@app.get("/api/v1/evaluate/stream")
async def evaluate_stream(
    symbol: str = Query(..., min_length=1, max_length=12),
    peers: str = Query(""),
) -> StreamingResponse:
    ctx = get_ctx()
    sym = symbol.upper().strip()

    async def event_generator():
        try:
            async for event in ctx.service.stream_evaluation(sym, peers):
                payload = {"type": event.type, "data": event.data}
                yield f"data: {json.dumps(payload)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'data': ''})}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'data': str(exc)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.delete("/api/v1/cache")
def clear_cache() -> JSONResponse:
    ctx = get_ctx()
    ctx.cache.clear()
    return JSONResponse({"status": "ok", "message": "Cache cleared"})


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
