from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from ..state import state

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
        app_router = state.router
        if proxy is None or app_router is None or proxy._transport is None:
            logger.warning("Rescan aborted: proxy or transport not available.")
            return

        backend_names = proxy._transport.running_backends()
        await app_router.build(proxy._transport, backend_names)

        # Re-run tool discovery
        if proxy.discovery is not None:
            new_discovery_result = await proxy.discovery.rescan()
            state.discovery = proxy.discovery

            # Re-run toxic flow analysis with fresh discovery data
            if proxy.toxic_flow is not None and new_discovery_result:
                try:
                    tf_result = proxy.toxic_flow.run(new_discovery_result)
                    state.toxic_flow = proxy.toxic_flow
                    logger.info(
                        "Toxic flow re-analysis complete. Severity: %s",
                        tf_result.get("session_severity", "unknown"),
                    )
                except Exception as tf_exc:
                    logger.error("Toxic flow re-analysis failed: %s", tf_exc)

            logger.info("Rescan complete. Routing table + discovery + toxic flow rebuilt.")
        else:
            logger.info("Rescan complete. Routing table rebuilt (no discovery instance).")
    except Exception as exc:
        logger.error("Rescan failed: %s", exc)
