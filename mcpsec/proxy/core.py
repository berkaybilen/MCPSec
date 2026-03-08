from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from config import MCPSecConfig
from proxy.base import MCPMessage
from proxy.router import Router, ToolNotFoundError
from proxy.session import Session, SessionEvent, SessionManager
from proxy.stdio_transport import StdioTransport

logger = logging.getLogger("proxy.core")


class ProxyCore:
    def __init__(self, config: MCPSecConfig) -> None:
        self._config = config
        self._session_manager = SessionManager()
        self._router = Router()
        self._transport: StdioTransport | None = None
        self._running = False
        self._current_session: Session | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def router(self) -> Router:
        return self._router

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    async def start(self) -> None:
        logger.info("ProxyCore starting...")
        self._transport = StdioTransport(self._config.backends)
        await self._transport.start()

        backend_names = self._transport.running_backends()
        if backend_names:
            await self._router.build(self._transport, backend_names)
        else:
            logger.warning("No backends available; routing table is empty.")

        self._running = True
        await self._message_loop()

    async def stop(self) -> None:
        logger.info("ProxyCore stopping...")
        self._running = False
        if self._transport:
            await self._transport.close()

    async def _message_loop(self) -> None:
        assert self._transport is not None

        while self._running:
            try:
                msg = await self._transport.receive_message()
            except EOFError:
                logger.info("Client disconnected (EOF on stdin).")
                break
            except Exception as exc:
                logger.error("Failed to read client message: %s\n%s", exc, traceback.format_exc())
                continue

            try:
                await self._handle_message(msg)
            except Exception as exc:
                logger.error(
                    "Unhandled exception processing message: %s\n%s", exc, traceback.format_exc()
                )
                err = MCPMessage.make_error(msg.id, -32000, f"Internal proxy error: {exc}")
                await self._transport.send_to_client(err)

    async def _handle_message(self, msg: MCPMessage) -> None:
        assert self._transport is not None

        if msg.method == "initialize":
            await self._handle_initialize(msg)
        elif msg.method == "tools/list":
            await self._handle_tools_list(msg)
        elif msg.method == "tools/call":
            await self._handle_tools_call(msg)
        else:
            await self._handle_fallback(msg)

    async def _handle_initialize(self, msg: MCPMessage) -> None:
        assert self._transport is not None

        session = self._session_manager.create_session()
        self._current_session = session
        logger.info("Session created: %s", session.session_id)

        # Forward to all backends; merge capabilities if needed
        backend_names = self._transport.running_backends()
        if not backend_names:
            err = MCPMessage.make_error(msg.id, -32000, "No backends available.")
            await self._transport.send_to_client(err)
            return

        # Forward to first backend and relay response
        response = await self._transport.send_to_backend(backend_names[0], msg)
        await self._transport.send_to_client(response)

    async def _handle_tools_list(self, msg: MCPMessage) -> None:
        assert self._transport is not None

        # Aggregate tool lists from all backends
        all_tools: list[dict[str, Any]] = []
        for backend_name in self._transport.running_backends():
            resp = await self._transport.send_to_backend(backend_name, msg)
            if resp.result:
                all_tools.extend(resp.result.get("tools", []))

        response = MCPMessage(
            id=msg.id,
            result={"tools": all_tools},
            raw={},
        )
        await self._transport.send_to_client(response)

    async def _handle_tools_call(self, msg: MCPMessage) -> None:
        assert self._transport is not None

        tool_name: str = msg.params.get("name", "")
        if not tool_name:
            err = MCPMessage.make_error(msg.id, -32602, "Missing tool name in params.")
            await self._transport.send_to_client(err)
            return

        # Resolve backend
        try:
            backend_name = self._router.resolve(tool_name)
        except ToolNotFoundError as exc:
            err = MCPMessage.make_error(msg.id, -32601, str(exc))
            await self._transport.send_to_client(err)
            return

        # Ensure we have a session
        if self._current_session is None:
            self._current_session = self._session_manager.create_session()
            logger.info(
                "Auto-created session: %s", self._current_session.session_id
            )

        session = self._current_session
        session.check_and_reset_timeout(self._config.session.alert_timeout_minutes)

        # Record request event
        request_event = SessionEvent(
            timestamp=datetime.now(tz=timezone.utc),
            direction="request",
            tool_name=tool_name,
            content=msg.params,
        )
        session.add_event(request_event)
        await _broadcast_event(session.session_id, request_event)

        # TODO: run analysis pipeline here (regex, chain tracking, enforcement)

        # Forward to backend
        response = await self._transport.send_to_backend(backend_name, msg)

        # Record response event
        response_event = SessionEvent(
            timestamp=datetime.now(tz=timezone.utc),
            direction="response",
            tool_name=tool_name,
            content=response.result or response.error or {},
        )
        session.add_event(response_event)
        await _broadcast_event(session.session_id, response_event)

        await self._transport.send_to_client(response)

    async def _handle_fallback(self, msg: MCPMessage) -> None:
        assert self._transport is not None

        backend_names = self._transport.running_backends()
        if not backend_names:
            err = MCPMessage.make_error(msg.id, -32000, "No backends available.")
            await self._transport.send_to_client(err)
            return

        response = await self._transport.send_to_backend(backend_names[0], msg)
        await self._transport.send_to_client(response)


async def _broadcast_event(session_id: str, event: SessionEvent) -> None:
    """Forward event to WebSocket broadcaster (imported lazily to avoid circular imports)."""
    try:
        from api.websocket import broadcast_event  # noqa: PLC0415
        await broadcast_event(session_id, event)
    except Exception:
        pass
