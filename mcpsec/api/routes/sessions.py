from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/sessions/{session_id}/chain-state")
async def get_chain_state(session_id: str) -> dict[str, Any]:
    proxy = state.proxy
    if proxy is None or proxy.chain_tracker is None:
        raise HTTPException(status_code=503, detail="Chain tracker not initialized.")

    session = proxy.session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    return proxy.chain_tracker.get_chain_state(session)
