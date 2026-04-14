from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api")


@router.get("/events")
async def get_events(
    session_id: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    flags_contain: str | None = Query(default=None, description="e.g. injection_detected"),
    since: str | None = Query(default=None, description="ISO timestamp lower bound"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    from ...storage.repository import EventRepository  # noqa: PLC0415
    repo = EventRepository()
    return repo.get_events(
        session_id=session_id,
        tool_name=tool_name,
        decision=decision,
        flags_contain=flags_contain,
        since=since,
        limit=limit,
    )


@router.get("/events/stats")
async def get_event_stats() -> dict[str, Any]:
    from ...storage.repository import EventRepository  # noqa: PLC0415
    repo = EventRepository()
    return repo.get_stats()
