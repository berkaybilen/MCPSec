from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ..state import state
from ...analysis.chain_tracker import ChainTracker, reconstruct_chain_state
from ...proxy.session import reconstruct_session_state
from ...storage.repository import EventRepository

router = APIRouter(prefix="/api")


@router.get("/sessions")
async def get_sessions(
    include_closed: bool = Query(default=True),
    limit: int = Query(default=100, ge=1),
) -> list[dict[str, Any]]:
    repo = EventRepository()
    return repo.get_sessions(include_closed=include_closed, limit=limit)


@router.get("/sessions/{session_id}/chain-state")
async def get_chain_state(session_id: str) -> dict[str, Any]:
    repo = EventRepository()
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    events = repo.get_events(session_id=session_id, limit=1000)
    routing = repo.get_routing_table().get("tool_to_backend", {})

    if state.config is None:
        raise HTTPException(status_code=503, detail="Config not loaded.")

    tracker = state.proxy.chain_tracker if state.proxy is not None else None
    if tracker is None:
        tracker = ChainTracker(
            state.config.chain_tracking,
            state.config.chain_tracking.result_path,
        )

    session_context = reconstruct_session_state(
        list(reversed(events)),
        label_getter=tracker.get_labels,
        sanitizer_tools=state.config.state_machine.sanitizer_tools,
    )

    return reconstruct_chain_state(
        tracker,
        session_id=session_id,
        session_state=session_context["state"],
        events=list(reversed(events)),
        routing_table=routing,
        state_changed_at=session_context["state_changed_at"],
        last_transition_reason=session_context["last_transition_reason"],
    ) | {"display_state": session["display_state"]}
