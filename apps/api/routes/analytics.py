import asyncio
import json
import os
from dataclasses import asdict

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from apps.api.dependencies.jwt_auth import require_analytics_access as require_analytics_token
from services.analytics_service.aggregator import (
    get_channel_metrics,
    get_intent_metrics,
    get_overview,
    get_realtime_events,
    get_sentiment_metrics,
    get_solution_performance,
    get_ticket_trend,
    get_agent_metrics,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])

_SSE_INTERVAL_SECONDS = 30


def _db() -> str:
    return os.getenv("DATABASE_PATH", "data/cx_phase1.db")


@router.get("/overview")
def overview(_: dict = Depends(require_analytics_token)) -> dict:
    return asdict(get_overview(_db()))


@router.get("/channels")
def channels(_: dict = Depends(require_analytics_token)) -> dict:
    return asdict(get_channel_metrics(_db()))


@router.get("/intents")
def intents(_: dict = Depends(require_analytics_token)) -> dict:
    return asdict(get_intent_metrics(_db()))


@router.get("/sentiment")
def sentiment(_: dict = Depends(require_analytics_token)) -> dict:
    return asdict(get_sentiment_metrics(_db()))


@router.get("/agents")
def agents(_: dict = Depends(require_analytics_token)) -> list:
    return [asdict(a) for a in get_agent_metrics(_db())]


@router.get("/trend")
def trend(_: dict = Depends(require_analytics_token)) -> list:
    return [asdict(t) for t in get_ticket_trend(_db())]


@router.get("/solution-performance")
def solution_performance(_: dict = Depends(require_analytics_token)) -> dict:
    return asdict(get_solution_performance(_db()))


@router.get("/events")
def events(_: dict = Depends(require_analytics_token)) -> list:
    return [asdict(e) for e in get_realtime_events(_db())]


@router.get("/stream")
async def stream(authorization: str | None = None) -> StreamingResponse:
    """SSE endpoint — pushes an overview snapshot every 30 s."""

    async def event_generator():
        while True:
            try:
                data = json.dumps(asdict(get_overview(_db())))
                yield f"data: {data}\n\n"
            except Exception:
                yield "data: {}\n\n"
            await asyncio.sleep(_SSE_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
