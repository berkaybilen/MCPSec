from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..proxy.session import SessionEvent

logger = logging.getLogger("api.websocket")

router = APIRouter()

_connections: set[WebSocket] = set()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket) -> None:
    await websocket.accept()
    _connections.add(websocket)
    logger.info("WebSocket client connected. Total: %d", len(_connections))
    try:
        while True:
            # Keep the connection alive; client can send pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(_connections))


async def broadcast_event(session_id: str, event: SessionEvent) -> None:
    if not _connections:
        return

    payload: dict[str, Any] = event.to_dict()
    payload["session_id"] = session_id

    dead: set[WebSocket] = set()
    for ws in list(_connections):
        try:
            await ws.send_json(payload)
        except Exception:
            dead.add(ws)

    for ws in dead:
        _connections.discard(ws)
