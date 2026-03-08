from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal


class SessionState(str, Enum):
    NORMAL = "NORMAL"
    ALERT = "ALERT"


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
        self.state: SessionState = SessionState.NORMAL
        self.alert_triggered_at: datetime | None = None
        self.events: list[SessionEvent] = []

    def add_event(self, event: SessionEvent) -> None:
        self.events.append(event)

    def transition_to_alert(self) -> None:
        self.state = SessionState.ALERT
        self.alert_triggered_at = datetime.now(tz=timezone.utc)

    def check_and_reset_timeout(self, timeout_minutes: int) -> None:
        if self.state == SessionState.ALERT and self.alert_triggered_at is not None:
            now = datetime.now(tz=timezone.utc)
            elapsed = (now - self.alert_triggered_at).total_seconds() / 60
            if elapsed >= timeout_minutes:
                self.state = SessionState.NORMAL
                self.alert_triggered_at = None

    def get_window(self, size: int) -> list[SessionEvent]:
        if self.state == SessionState.ALERT and self.alert_triggered_at is not None:
            return [e for e in self.events if e.timestamp >= self.alert_triggered_at]
        return self.events[-size:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "state": self.state.value,
            "alert_triggered_at": (
                self.alert_triggered_at.isoformat() if self.alert_triggered_at else None
            ),
            "event_count": len(self.events),
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
