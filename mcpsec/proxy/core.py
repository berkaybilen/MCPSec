from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from ..analysis.regex_filter import analyze_request, analyze_response, redact_credentials
from ..config import MCPSecConfig
from ..discovery.discovery import ToolDiscovery
from ..enforcement.engine import decide
from ..storage.repository import EventRepository
from .base import MCPMessage
from .router import Router, ToolNotFoundError
from .session import Session, SessionEvent, SessionManager
from .stdio_transport import StdioTransport

logger = logging.getLogger("proxy.core")


class ProxyCore:
    def __init__(self, config: MCPSecConfig, no_backends: bool = False) -> None:
        self._config = config
        self._no_backends = no_backends
        self._session_manager = SessionManager()
        self._router = Router()
        self._transport: StdioTransport | None = None
        self._running = False
        self._current_session: Session | None = None
        self.discovery: ToolDiscovery | None = None
        self._discovery_started = False
        self._tools_cache: list[dict[str, Any]] | None = None
        self.toxic_flow: Any | None = None  # ToxicFlowAnalyzer, set after discovery
        self.chain_tracker: Any | None = None  # ChainTracker, set after toxic flow
        self.anomaly_detector: Any | None = None  # AnomalyDetector, initialized at startup
        self._repo = EventRepository()

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
        backends = [] if self._no_backends else self._config.backends
        self._transport = StdioTransport(backends)
        await self._transport.start()

        # Routing table and discovery are deferred until after initialize
        # handshake. MCP protocol requires initialize before any other
        # request — Gmail MCP enforces this strictly.
        self._running = True
        if not self._no_backends:
            await self._message_loop()
        else:
            # API-only mode: no message loop, just keep alive until stopped
            while self._running:
                await asyncio.sleep(1)

    async def stop(self) -> None:
        logger.info("ProxyCore stopping...")
        self._running = False
        if self._transport:
            await self._transport.close()

    async def _run_discovery(self) -> None:
        discovery_result: dict = {}
        try:
            discovery_result = await self.discovery.run()
            logger.info(
                "Discovery complete: %d backends processed.",
                len(discovery_result.get("backends", {})),
            )
        except Exception as exc:
            logger.error("Tool discovery failed (non-fatal): %s", exc)

        # Toxic flow analysis — runs after discovery completes
        if discovery_result:
            try:
                from ..analysis.toxic_flow import ToxicFlowAnalyzer  # noqa: PLC0415
                self.toxic_flow = ToxicFlowAnalyzer(
                    self._config.toxic_flow,
                    self._config.toxic_flow.result_path,
                )
                tf_result = self.toxic_flow.run(discovery_result)
                logger.info(
                    "Toxic flow analysis complete. Session severity: %s",
                    tf_result["session_severity"],
                )
            except ImportError:
                logger.debug("ToxicFlowAnalyzer not yet available, skipping.")
            except Exception as exc:
                logger.error("Toxic flow analysis failed (non-fatal): %s", exc)

        # Chain tracking — runs after toxic flow (needs label map from result)
        if self._config.chain_tracking.enabled:
            try:
                from ..analysis.chain_tracker import ChainTracker  # noqa: PLC0415
                self.chain_tracker = ChainTracker(
                    self._config.chain_tracking,
                    self._config.chain_tracking.result_path,
                )
                logger.info("ChainTracker initialized.")
            except Exception as exc:
                logger.error("ChainTracker init failed (non-fatal): %s", exc)

        # Anomaly detection — global, session-independent frequency + off-hours
        if self._config.anomaly_detection.enabled:
            try:
                from ..analysis.anomaly_detector import AnomalyDetector  # noqa: PLC0415
                self.anomaly_detector = AnomalyDetector(self._config.anomaly_detection)
                logger.info("AnomalyDetector initialized.")
            except Exception as exc:
                logger.error("AnomalyDetector init failed (non-fatal): %s", exc)

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
        self._repo.upsert_session(session.session_id, session.created_at.isoformat(), session.state.value, 0)

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
            self._repo.save_routing_table(self._router.get_routing_table())

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

        # Request analysis — regex filter
        req_flags = analyze_request(tool_name, msg.params)
        req_result = decide(
            req_flags,
            self._config.enforcement.default_mode,
            rules_file=self._config.enforcement.rules_file,
            session_state=session.state.value,
        )
        request_event.flags = req_flags
        request_event.decision = req_result.decision

        self._repo.save_event(session.session_id, request_event.to_dict())
        self._repo.upsert_session(session.session_id, session.created_at.isoformat(), session.state.value, len(session.events))

        if req_result.is_blocking:
            logger.warning("BLOCKED request: tool=%s flags=%s", tool_name, req_flags)
            err = MCPMessage.make_error(msg.id, -32000, f"Blocked by MCPSec: {req_flags}")
            await self._transport.send_to_client(err)
            return

        # Chain tracking — runs after regex filter
        if self.chain_tracker is not None:
            event_id = len(session.events)
            ct_result = self.chain_tracker.check(session, tool_name, event_id, backend_name)
            if ct_result.matched_combination:
                logger.warning(
                    "Chain tracking: combination=%s step=%s decision=%s tool=%s",
                    ct_result.matched_combination,
                    ct_result.step,
                    ct_result.decision,
                    tool_name,
                )
                request_event.flags = list(request_event.flags) + [
                    f"chain:{ct_result.matched_combination}:{ct_result.step}"
                ]
                if ct_result.decision in ("ALERT", "BLOCK"):
                    await _broadcast_chain_event(session.session_id, tool_name, ct_result)
            if ct_result.decision == "BLOCK":
                combo = ct_result.matched_combination or "unknown"
                step = ct_result.step or "?"
                err = MCPMessage.make_error(
                    msg.id,
                    -32600,
                    f"MCPSec: Tool call blocked — dangerous chain detected ({combo}, step {step}). "
                    f"Tool '{tool_name}' continues a {combo} chain.",
                )
                request_event.decision = "block"
                self._repo.save_event(session.session_id, request_event.to_dict())
                await self._transport.send_to_client(err)
                return

        # Anomaly detection — frequency + off-hours (global, session-independent)
        if self.anomaly_detector is not None:
            anomaly_flags = self.anomaly_detector.check()
            if anomaly_flags:
                anomaly_result = decide(
                    anomaly_flags,
                    self._config.enforcement.default_mode,
                    rules_file=self._config.enforcement.rules_file,
                    session_state=session.state.value,
                )
                logger.warning(
                    "Anomaly detected: flags=%s decision=%s tool=%s",
                    anomaly_flags,
                    anomaly_result.decision,
                    tool_name,
                )
                request_event.flags = list(request_event.flags) + anomaly_flags
                if anomaly_result.is_blocking:
                    request_event.decision = "block"
                    self._repo.save_event(session.session_id, request_event.to_dict())
                    err = MCPMessage.make_error(
                        msg.id,
                        -32000,
                        f"Blocked by MCPSec: anomaly detected ({anomaly_flags})",
                    )
                    await self._transport.send_to_client(err)
                    return

        # Forward to backend
        response = await self._transport.send_to_backend(backend_name, msg)

        # Response analysis
        resp_content = response.result or response.error or {}
        resp_flags = analyze_response(tool_name, resp_content)
        resp_result = decide(
            resp_flags,
            self._config.enforcement.default_mode,
            rules_file=self._config.enforcement.rules_file,
            session_state=session.state.value,
        )

        # Session ALERT transition on injection_detected in response
        if "injection_detected" in resp_flags and session.state.value == "NORMAL":
            session.transition_to_alert()
            logger.warning("Session transitioned to ALERT: injection_detected in response of tool=%s", tool_name)

        # Redact credentials from response before forwarding to client
        if resp_result.redact:
            resp_content = redact_credentials(resp_content)
            if response.result is not None:
                response = MCPMessage(
                    id=response.id,
                    method=response.method,
                    result=resp_content,
                    error=response.error,
                    raw=response.raw,
                )
            logger.info("Redacted credentials in response: tool=%s", tool_name)

        if req_flags:
            logger.warning("REQUEST  flags=%s decision=%s tool=%s", req_flags, req_result.decision, tool_name)
        if resp_flags:
            logger.warning("RESPONSE flags=%s decision=%s redact=%s tool=%s", resp_flags, resp_result.decision, resp_result.redact, tool_name)

        response_event = SessionEvent(
            timestamp=datetime.now(tz=timezone.utc),
            direction="response",
            tool_name=tool_name,
            content=resp_content,
            flags=resp_flags,
            decision=resp_result.decision,
        )
        session.add_event(response_event)
        await _broadcast_event(session.session_id, response_event)
        self._repo.save_event(session.session_id, response_event.to_dict())
        self._repo.upsert_session(session.session_id, session.created_at.isoformat(), session.state.value, len(session.events))

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


async def _broadcast_chain_event(session_id: str, tool_name: str, ct_result: Any) -> None:
    """Broadcast chain tracking alert/block over WebSocket."""
    try:
        from ..api.websocket import broadcast_raw  # noqa: PLC0415
        event_type = (
            "chain_tracking_block" if ct_result.decision == "BLOCK" else "chain_tracking_alert"
        )
        await broadcast_raw({
            "type": event_type,
            "session_id": session_id,
            "decision": ct_result.decision,
            "matched_combination": ct_result.matched_combination,
            "step": ct_result.step,
            "tool": tool_name,
            "context": ct_result.context,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })
    except Exception:
        pass
