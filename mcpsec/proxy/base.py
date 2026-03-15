from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class MCPMessage:
    id: str | int | None = None
    method: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MCPMessage":
        return cls(
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params") or {},
            result=data.get("result"),
            error=data.get("error"),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        msg: dict[str, Any] = {"jsonrpc": "2.0"}
        if self.id is not None:
            msg["id"] = self.id
        if self.method is not None:
            msg["method"] = self.method
            msg["params"] = self.params
        if self.result is not None:
            msg["result"] = self.result
        if self.error is not None:
            msg["error"] = self.error
        return msg

    @staticmethod
    def make_error(msg_id: str | int | None, code: int, message: str) -> "MCPMessage":
        return MCPMessage(
            id=msg_id,
            error={"code": code, "message": f"MCPSec: {message}"},
            raw={},
        )


class BaseTransport(ABC):
    @abstractmethod
    async def receive_message(self) -> MCPMessage:
        """Read the next message from the client."""

    @abstractmethod
    async def send_to_client(self, msg: MCPMessage) -> None:
        """Send a message back to the client."""

    @abstractmethod
    async def send_to_backend(self, backend_name: str, msg: MCPMessage) -> MCPMessage:
        """Forward a message to a specific backend and return its response."""

    @abstractmethod
    async def send_notification_to_backend(self, backend_name: str, msg: "MCPMessage") -> None:
        """Send a message to a backend without waiting for a response."""

    @abstractmethod
    async def close(self) -> None:
        """Terminate all backend processes and clean up."""
