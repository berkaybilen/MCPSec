from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config import MCPSecConfig
    from discovery.discovery import ToolDiscovery
    from proxy.core import ProxyCore
    from proxy.router import Router
    from proxy.session import SessionManager


class AppState:
    proxy: "ProxyCore | None" = None
    router: "Router | None" = None
    sessions: "SessionManager | None" = None
    config: "MCPSecConfig | None" = None
    discovery: "ToolDiscovery | None" = None


state = AppState()
