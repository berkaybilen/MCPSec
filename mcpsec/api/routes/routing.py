from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..state import state

router = APIRouter(prefix="/api")


@router.get("/routing-table")
async def get_routing_table() -> dict[str, Any]:
    from ...storage.repository import EventRepository  # noqa: PLC0415
    repo = EventRepository()
    return repo.get_routing_table()
