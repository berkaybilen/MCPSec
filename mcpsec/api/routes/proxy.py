from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException

from ..state import state

router = APIRouter(prefix="/api/proxy")


@router.post("/start")
async def start_proxy() -> dict[str, Any]:
    if state.proxy is None:
        raise HTTPException(status_code=503, detail="Proxy not initialized.")
    if state.proxy.is_running:
        raise HTTPException(status_code=409, detail="Proxy is already running.")
    asyncio.create_task(state.proxy.start())
    return {"status": "starting"}


@router.post("/stop")
async def stop_proxy() -> dict[str, Any]:
    if state.proxy is None:
        raise HTTPException(status_code=503, detail="Proxy not initialized.")
    if not state.proxy.is_running:
        raise HTTPException(status_code=409, detail="Proxy is not running.")
    await state.proxy.stop()
    return {"status": "stopped"}
