from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from ..analysis.regex_filter import analyze_request, analyze_response
from ..config import MCPSecConfig
from ..discovery.discovery import ToolDiscovery
from ..enforcement.engine import decide
from .base import MCPMessage
from .router import Router, ToolNotFoundError
from .session import Session, SessionEvent, SessionManager
from .stdio_transport import StdioTransport

logger = logging.getLogger("proxy.core")


class ProxyCore:
    def __init__(self, config: MCPSecConfig) -> None:
        self._config = config
        self._session_manager = SessionManager()
        self._router = Router()
        self._transport: StdioTransport | None = None
        self._running = False
        self._current_session: Session | None = None
        self.discovery: ToolDiscovery | None = None
        self._discovery_started = False
        self._tools_cache: list[dict[str, Any]] | None = None

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

        # Routing table and discovery are deferred until after initialize
        # handshake. MCP protocol requires initialize before any other
        # request — Gmail MCP enforces this strictly.
        self._running = True
        await self._message_loop()

    async def stop(self) -> None:
        logger.info("ProxyCore stopping...")
        self._running = False
        if self._transport:
            await self._transport.close()

    async def _run_discovery(self) -> None:
        try:
            discovery_result = await self.discovery.run()
            logger.info(
                "Discovery complete: %d backends processed.",
                len(discovery_result.get("backends", {})),
            )
        except Exception as exc:
            logger.error("Tool discovery failed (non-fatal): %s", exc)

    async def _message_loop(self) -> None:
        assert self._transport is not None
        logger.debug("Message loop started. Routing table: %s", self._router.get_routing_table())

        while self._running:
            try:
                msg = await self._transport.receive_message()
                logger.debug("<<< client  method=%s id=%s params=%s", msg.method, msg.id, msg.params)
            except EOFError:
                logger.info("Client disconnected (EOF on stdin).")
                break
            except Exception as exc:
                logger.error("Failed to read client message: %s\n%s", exc, traceback.format_exc())
                continue

            try:
                await self._handle_message(msg)
                logger.debug(">>> handled method=%s id=%s", msg.method, msg.id)
            except Exception as exc:
                logger.error(
                    "Unhandled exception processing message: %s\n%s", exc, traceback.format_exc()
                )
                err = MCPMessage.make_error(msg.id, -32000, f"Internal proxy error: {exc}")
                await self._transport.send_to_client(err)

    async def _handle_message(self, msg: MCPMessage) -> None:
        assert self._transport is not None

        # JSON-RPC response (no method) — forward to backend, no reply expected
        if msg.method is None:
            logger.debug("Forwarding JSON-RPC response id=%s to backends", msg.id)
            await self._handle_response(msg)
            return

        # Notification (no id) — fire-and-forget to all backends, no reply expected
        if msg.id is None:
            logger.debug("Forwarding notification method=%s to backends", msg.method)
            await self._handle_notification(msg)
            return

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

        backend_names = self._transport.running_backends()

        # Step 1: Initialize all backends (MCP protocol handshake)
        for backend_name in backend_names:
            await self._transport.send_to_backend(backend_name, msg)
            logger.debug("Backend '%s' initialized", backend_name)

        # Step 2: Send 'initialized' notification to all backends
        # MCP spec requires this before any tools/list or tools/call.
        initialized_notif = MCPMessage(
            method="notifications/initialized",
            params={},
            raw={},
        )
        for backend_name in backend_names:
            await self._transport.send_notification_to_backend(backend_name, initialized_notif)

        # Step 3: Respond to client ASAP — routing table will be built on first tools/list
        response = MCPMessage(
            id=msg.id,
            result={
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mcpsec", "version": "0.1.0"},
            },
            raw={},
        )
        await self._transport.send_to_client(response)

    async def _handle_tools_list(self, msg: MCPMessage) -> None:
        import asyncio

        assert self._transport is not None

        if self._tools_cache is not None:
            # Return cached tools — don't go to backends again
            logger.info("tools/list returning %d cached tools", len(self._tools_cache))
        else:
            # First call: build routing table (which queries tools/list from all backends)
            backend_names = self._transport.running_backends()
            self._tools_cache = await self._router.build(self._transport, backend_names)
            logger.info("tools/list fetched %d tools from backends", len(self._tools_cache))

        response = MCPMessage(
            id=msg.id,
            result={"tools": self._tools_cache},
            raw={},
        )
        await self._transport.send_to_client(response)

        # Start discovery AFTER first tools/list completes — both initialize
        # and tools/list are done, so discovery won't block the client.
        if not self._discovery_started:
            self._discovery_started = True
            backend_names = self._transport.running_backends()
            self.discovery = ToolDiscovery(self._transport, backend_names, self._config)
            asyncio.create_task(self._run_discovery())

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
            logger.debug("tool '%s' resolved to backend '%s'", tool_name, backend_name)
        except ToolNotFoundError as exc:
            logger.warning("BLOCKED tools/call: %s | routing table: %s", exc, self._router.get_routing_table())
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

        # Request analysis
        req_flags = analyze_request(tool_name, msg.params)
        req_decision = decide(req_flags, self._config.enforcement.default_mode)
        request_event.flags = req_flags
        request_event.decision = req_decision

        if req_decision == "block":
            logger.warning("BLOCKED request: tool=%s flags=%s", tool_name, req_flags)
            err = MCPMessage.make_error(msg.id, -32000, f"Blocked by MCPSec: {req_flags}")
            await self._transport.send_to_client(err)
            return

        # Forward to backend
        response = await self._transport.send_to_backend(backend_name, msg)

        # Response analysis
        resp_content = response.result or response.error or {}
        resp_flags = analyze_response(tool_name, resp_content)
        resp_decision = decide(resp_flags, self._config.enforcement.default_mode)

        if req_flags:
            logger.warning("REQUEST  flags=%s decision=%s tool=%s", req_flags, req_decision, tool_name)
        if resp_flags:
            logger.warning("RESPONSE flags=%s decision=%s tool=%s", resp_flags, resp_decision, tool_name)

        response_event = SessionEvent(
            timestamp=datetime.now(tz=timezone.utc),
            direction="response",
            tool_name=tool_name,
            content=resp_content,
            flags=resp_flags,
            decision=resp_decision,
        )
        session.add_event(response_event)
        await _broadcast_event(session.session_id, response_event)

        await self._transport.send_to_client(response)

    async def _handle_notification(self, msg: MCPMessage) -> None:
        """Fire-and-forget: forward notification to all backends, no response expected."""
        assert self._transport is not None
        for backend_name in self._transport.running_backends():
            await self._transport.send_notification_to_backend(backend_name, msg)

    async def _handle_response(self, msg: MCPMessage) -> None:
        """Forward a JSON-RPC response (from client) back to the originating backend."""
        assert self._transport is not None
        # Best-effort: send to all backends — only the one that issued the request will care
        for backend_name in self._transport.running_backends():
            await self._transport.send_notification_to_backend(backend_name, msg)

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
        from ..api.websocket import broadcast_event  # noqa: PLC0415
        await broadcast_event(session_id, event)
    except Exception:
        pass
