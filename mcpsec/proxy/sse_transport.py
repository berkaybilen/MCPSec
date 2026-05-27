"""proxy/sse_transport.py — MCP HTTP+SSE transport.

MCP clients (Claude Code, Claude Desktop) connect here instead of
spawning the proxy via stdio.  The flow per client:

  1. GET /sse          → client gets an SSE stream + endpoint URL
  2. POST /messages    → client sends JSON-RPC messages here
  3. SSE stream        → proxy sends responses back to client

Multiple concurrent clients are supported; each gets its own queue.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .base import MCPMessage

logger = logging.getLogger("proxy.sse")

# session_id -> response queue (messages to send back to that MCP client)
_sse_queues: dict[str, asyncio.Queue] = {}


def create_mcp_sse_router(proxy_core: Any) -> APIRouter:
    """Return a FastAPI router that implements the MCP HTTP+SSE transport."""
    router = APIRouter()

    @router.get("/sse")
    async def sse_connect(request: Request) -> StreamingResponse:
        """MCP client connects here; receives response stream."""
        client_id = str(uuid.uuid4())
        queue: asyncio.Queue = asyncio.Queue()
        _sse_queues[client_id] = queue

        # Tell ProxyCore to route responses for this client to our queue
        async def send_fn(msg: MCPMessage) -> None:
            await queue.put(msg.to_dict())

        proxy_core.register_sse_client(client_id, send_fn)
        logger.info("SSE MCP client connected: id=%s  total=%d", client_id, len(_sse_queues))

        # The endpoint URL that the client will POST messages to
        messages_url = f"/messages?sessionId={client_id}"

        async def event_stream():
            # First message: tell client where to POST requests.
            # MCP SSE spec: endpoint event data is a plain URL string (NOT JSON-encoded).
            yield f"event: endpoint\ndata: {messages_url}\n\n"

            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                        if msg is None:
                            break
                        yield f"data: {json.dumps(msg)}\n\n"
                    except asyncio.TimeoutError:
                        # SSE keepalive comment — keeps the connection alive through proxies
                        yield ": ping\n\n"
            finally:
                _sse_queues.pop(client_id, None)
                proxy_core.unregister_sse_client(client_id)
                logger.info("SSE MCP client disconnected: id=%s", client_id)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @router.post("/messages")
    async def receive_message(sessionId: str, request: Request) -> dict:
        """MCP client POSTs JSON-RPC requests here."""
        try:
            body = await request.json()
        except Exception as exc:
            return {"error": f"Invalid JSON: {exc}"}

        msg = MCPMessage.from_dict(body)
        logger.debug("SSE← client=%s method=%s id=%s", sessionId, msg.method, msg.id)
        await proxy_core.handle_sse_message(msg, sessionId)
        return {"status": "accepted"}

    return router
