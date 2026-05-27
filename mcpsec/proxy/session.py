from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class SessionState(str, Enum):
    SAFE = "SAFE"
    TAINTED = "TAINTED"
    SANITIZED = "SANITIZED"


def _error_payload(content: Any) -> bool:
    return isinstance(content, dict) and "code" in content and "message" in content and "content" not in content


def advance_session_state(
    current_state: SessionState,
    *,
    direction: Literal["request", "response"],
    tool_name: str,
    tool_labels: list[str],
    flags: list[str] | None = None,
    content: Any = None,
    sanitizer_tools: list[str] | None = None,
) -> tuple[SessionState, str | None]:
    flags = flags or []
    sanitizer_tools = sanitizer_tools or []

    if direction == "request" and "U" in tool_labels:
        return SessionState.TAINTED, f"Untrusted tool call: {tool_name}"

    if direction == "response":
        if "injection_detected" in flags:
            return SessionState.TAINTED, f"Injection detected in response: {tool_name}"
        if (
            tool_name in sanitizer_tools
            and current_state == SessionState.TAINTED
            and not _error_payload(content)
        ):
            return SessionState.SANITIZED, f"Sanitized by tool: {tool_name}"

    return current_state, None


@dataclass
class SessionEvent:
    timestamp: datetime
    direction: Literal["request", "response"]
    tool_name: str
    content: dict[str, Any]
    flags: list[str] = field(default_factory=list)
    decision: Literal["pass", "block", "alert", "log"] = "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction,
            "tool_name": self.tool_name,
            "content": self.content,
            "flags": self.flags,
            "decision": self.decision,
        }


class Session:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.created_at: datetime = datetime.now(tz=timezone.utc)
        self.state: SessionState = SessionState.SAFE
        self.state_changed_at: datetime = self.created_at
        self.last_transition_reason: str | None = None
        self.events: list[SessionEvent] = []
        self.tool_sequence: list[Any] = []  # list[ToolSequenceEntry], typed in chain_tracker

    def add_event(self, event: SessionEvent) -> None:
        self.events.append(event)

    def transition_state(self, new_state: SessionState, reason: str | None = None) -> None:
        if new_state == self.state:
            return
        self.state = new_state
        self.state_changed_at = datetime.now(tz=timezone.utc)
        self.last_transition_reason = reason

    def apply_request_context(self, tool_name: str, tool_labels: list[str]) -> None:
        next_state, reason = advance_session_state(
            self.state,
            direction="request",
            tool_name=tool_name,
            tool_labels=tool_labels,
        )
        self.transition_state(next_state, reason)

    def apply_response_context(
        self,
        tool_name: str,
        tool_labels: list[str],
        flags: list[str],
        content: Any,
        sanitizer_tools: list[str],
    ) -> None:
        next_state, reason = advance_session_state(
            self.state,
            direction="response",
            tool_name=tool_name,
            tool_labels=tool_labels,
            flags=flags,
            content=content,
            sanitizer_tools=sanitizer_tools,
        )
        self.transition_state(next_state, reason)

    def get_window(self, size: int) -> list[SessionEvent]:
        return self.events[-size:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "state": self.state.value,
            "state_changed_at": self.state_changed_at.isoformat(),
            "last_transition_reason": self.last_transition_reason,
            "event_count": len(self.events),
        }


def reconstruct_session_state(
    events: list[dict[str, Any]],
    *,
    label_getter: Any,
    sanitizer_tools: list[str],
) -> dict[str, Any]:
    state = SessionState.SAFE
    changed_at: str | None = None
    reason: str | None = None

    for event in events:
        tool_name = event.get("tool_name", "")
        tool_labels = label_getter(tool_name)
        next_state, next_reason = advance_session_state(
            state,
            direction=event["direction"],
            tool_name=tool_name,
            tool_labels=tool_labels,
            flags=event.get("flags", []),
            content=event.get("content"),
            sanitizer_tools=sanitizer_tools,
        )
        if next_state != state:
            state = next_state
            changed_at = event.get("timestamp")
            reason = next_reason

    return {
        "state": state.value,
        "state_changed_at": changed_at,
        "last_transition_reason": reason,
    }


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(session_id)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            session = Session(session_id)
            self._sessions[session_id] = session
            return session
        return self._sessions[session_id]

    def close_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_all_sessions(self) -> list[Session]:
        return list(self._sessions.values())
