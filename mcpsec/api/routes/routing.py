from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from api.state import state

router = APIRouter(prefix="/api")


@router.get("/routing-table")
async def get_routing_table() -> dict[str, Any]:
    if state.router is None:
        return {}
    return state.router.get_all_tools()
