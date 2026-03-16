from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..state import state

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def get_sessions() -> list[dict[str, Any]]:
    if state.sessions is None:
        return []
    return [s.to_dict() for s in state.sessions.get_all_sessions()]
