from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from api.state import state

router = APIRouter(prefix="/api")
logger = logging.getLogger("api.rescan")


@router.post("/rescan")
async def trigger_rescan() -> dict[str, Any]:
    if state.proxy is None or state.router is None:
        raise HTTPException(status_code=503, detail="Proxy not initialized.")
    asyncio.create_task(_rescan_task())
    return {"status": "rescan_started"}


async def _rescan_task() -> None:
    try:
        logger.info("Rescan started.")
        proxy = state.proxy
        router = state.router
        if proxy is None or router is None or proxy._transport is None:
            logger.warning("Rescan aborted: proxy or transport not available.")
            return

        backend_names = proxy._transport.running_backends()
        await router.build(proxy._transport, backend_names)
        logger.info("Rescan complete. Routing table rebuilt.")
    except Exception as exc:
        logger.error("Rescan failed: %s", exc)
