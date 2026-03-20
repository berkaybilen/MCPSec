from __future__ import annotations

import logging

from .base import BaseTransport, MCPMessage

logger = logging.getLogger("proxy.router")


class ToolNotFoundError(Exception):
    pass


class Router:
    def __init__(self) -> None:
        # tool_name -> backend_name
        self._table: dict[str, str] = {}
        # backend_name -> [tool_names]
        self._backend_tools: dict[str, list[str]] = {}

    async def build(self, transport: BaseTransport, backend_names: list[str]) -> list[dict]:
        """Build routing table and return full tool definitions for tools/list response."""
        self._table.clear()
        self._backend_tools.clear()
        all_tool_defs: list[dict] = []

        for backend_name in backend_names:
            request = MCPMessage(
                id=1,
                method="tools/list",
                params={},
                raw={},
            )
            logger.debug("Querying tools/list from backend '%s'", backend_name)
            response = await transport.send_to_backend(backend_name, request)
            logger.debug("Backend '%s' tools/list response: result=%s error=%s", backend_name, response.result, response.error)

            if response.error:
                logger.warning(
                    "Backend '%s' returned error on tools/list: %s",
                    backend_name,
                    response.error,
                )
                self._backend_tools[backend_name] = []
                continue

            tools = []
            if response.result:
                tool_list = response.result.get("tools", [])
                for tool in tool_list:
                    tool_name = tool.get("name")
                    if not tool_name:
                        continue
                    if tool_name in self._table:
                        logger.warning(
                            "Tool name collision: '%s' already registered from '%s'. "
                            "Keeping first registration; ignoring '%s'.",
                            tool_name,
                            self._table[tool_name],
                            backend_name,
                        )
                    else:
                        self._table[tool_name] = backend_name
                        tools.append(tool_name)
                        all_tool_defs.append(tool)

            self._backend_tools[backend_name] = tools

        tool_count = len(self._table)
        backend_count = len(self._backend_tools)
        logger.info(
            "Routing table built: %d tools across %d backends.", tool_count, backend_count
        )
        return all_tool_defs

    def resolve(self, tool_name: str) -> str:
        backend = self._table.get(tool_name)
        if backend is None:
            raise ToolNotFoundError(f"Tool '{tool_name}' not found in routing table.")
        return backend

    def get_all_tools(self) -> dict[str, list[str]]:
        return dict(self._backend_tools)

    def get_routing_table(self) -> dict[str, str]:
        return dict(self._table)
