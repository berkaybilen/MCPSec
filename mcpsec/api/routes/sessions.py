from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..state import state

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def get_sessions(
    include_closed: bool = Query(default=True),
    limit: int = Query(default=100, ge=1),
) -> list[dict[str, Any]]:
    from ...storage.repository import EventRepository  # noqa: PLC0415
    repo = EventRepository()
    return repo.get_sessions(include_closed=include_closed, limit=limit)
