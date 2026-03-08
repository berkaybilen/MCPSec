from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from api.state import state

router = APIRouter(prefix="/api")


@router.get("/events")
async def get_events(
    session_id: str | None = Query(default=None),
    tool_name: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1),
) -> list[dict[str, Any]]:
    if state.sessions is None:
        return []

    results: list[dict[str, Any]] = []
    for session in state.sessions.get_all_sessions():
        if session_id and session.session_id != session_id:
            continue
        for event in session.events:
            if tool_name and event.tool_name != tool_name:
                continue
            if decision and event.decision != decision:
                continue
            entry = event.to_dict()
            entry["session_id"] = session.session_id
            results.append(entry)

    results.sort(key=lambda e: e["timestamp"], reverse=True)
    return results[:limit]
