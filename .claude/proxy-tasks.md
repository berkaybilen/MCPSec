# MCPSec — Proxy Module Tasks

## Context

This file covers implementation tasks for the `proxy/` and `api/` modules of MCPSec. Read `project-architecture.md` first for full project scope, directory structure, technology stack, and design patterns.

The proxy module is the foundation of the entire system. The API module runs alongside it in the same process, exposing live proxy state to any HTTP client or dashboard. All other modules (discovery, analysis, enforcement, storage) plug into the proxy.

Implement tasks in order — each one builds on the previous.

At the end of these tasks, MCPSec should be able to:
- Intercept tool calls between Claude and multiple MCP backend servers
- Maintain sessions with state machine
- Forward messages with no analysis yet
- Expose a fully working REST API and live WebSocket feed

---

## Module Responsibilities

**Proxy:**
- Spawn and manage backend MCP server processes (stdio)
- Relay JSON-RPC messages between client and backends
- Build and maintain a routing table (tool name → backend)
- Create and manage sessions (one per connection)
- Track session state (NORMAL / ALERT)
- Store all events in an in-memory trace per session
- Return MCP-compliant errors when backends fail

**API:**
- Expose REST endpoints for config, sessions, events, backends, rules, features
- Stream live events over WebSocket
- Share in-memory state with the proxy (same process, same objects)
- Allow config changes to hot-reload affected proxy modules

---

## File Overview

```
proxy/
├── base.py             # BaseTransport abstract class, MCPMessage dataclass
├── stdio_transport.py  # StdioTransport — spawns processes, reads/writes stdin/stdout
├── router.py           # Router — queries tools/list, builds routing table
├── session.py          # Session, SessionManager, state machine
└── core.py             # ProxyCore — orchestrates everything

api/
├── server.py           # FastAPI app, mounts all routers, starts uvicorn
├── state.py            # Shared in-memory state (proxy, router, sessions, repo)
├── websocket.py        # WebSocket endpoint — streams live events
└── routes/
    ├── events.py
    ├── sessions.py
    ├── routing.py
    ├── analysis.py
    ├── config.py
    ├── proxy.py
    ├── backends.py
    ├── rules.py
    ├── features.py
    └── rescan.py
```

---

## Tasks

---

### PROXY-01 — Project Skeleton

Create the top-level project structure. Nothing functional yet, just the scaffold.

**Create the following files and directories with minimal placeholder content:**

```
mcpsec/
├── main.py
├── config.py
├── mcpsec-config.yaml
├── proxy/
│   ├── __init__.py
│   ├── base.py
│   ├── stdio_transport.py
│   ├── router.py
│   ├── session.py
│   └── core.py
├── discovery/
│   └── __init__.py
├── analysis/
│   └── __init__.py
├── enforcement/
│   └── __init__.py
├── storage/
│   └── __init__.py
├── api/
│   ├── __init__.py
│   ├── server.py
│   ├── state.py
│   ├── websocket.py
│   └── routes/
│       └── __init__.py
└── tests/
    ├── unit/
    └── integration/
```

**`requirements.txt` must include:**
- `mcp` — official MCP Python SDK
- `pydantic` — config validation
- `pyyaml` — config file parsing
- `httpx` — async HTTP client (M2 HTTP transport)
- `fastapi` — REST API and WebSocket server
- `uvicorn` — ASGI server for FastAPI
- `pytest` — testing
- `pytest-asyncio` — async test support

**`mcpsec-config.yaml`** must include a working example config with at least two stdio backends, API settings, enforcement mode, session settings, and feature flags. See `project-architecture.md` for the full config structure.

**`main.py`** should be a stub that prints "MCPSec starting..." and exits cleanly.

**Acceptance check:** `python main.py` runs without errors.

---

### PROXY-02 — Config Loader

Implement `config.py`. This is the single source of truth for all runtime settings.

**Load `mcpsec-config.yaml` and parse it into Pydantic v2 models.**

The config model must cover:
- Proxy settings: transport mode (`stdio` or `http`), port
- API settings: port, enabled flag
- Backend list: name, transport type, command + args (stdio) or url (HTTP)
- Enforcement: default mode (block / alert / log), path to rules file
- Session settings: alert timeout in minutes, sliding window size
- Feature flags: embedding_filter, llm_evaluator, anomaly_detection, dashboard (all bool)

**Expose a `load_config(path: str) -> MCPSecConfig` function.** Raise a clear error with the field name if required fields are missing or types are wrong (Pydantic handles this automatically).

**Acceptance check:** Load the example config from PROXY-01, print the parsed model, no errors.

---

### PROXY-03 — BaseTransport and MCPMessage

Implement `proxy/base.py`.

**Define `MCPMessage` as a dataclass** with the following fields:
- `id` — str or int, the JSON-RPC message id
- `method` — str, e.g. `tools/call`, `tools/list`, `initialize`
- `params` — dict, the message parameters
- `result` — dict or None, present in responses
- `error` — dict or None, present in error responses
- `raw` — dict, the original unparsed message

**Define `BaseTransport` as an abstract base class** with these abstract async methods:
- `receive_message() -> MCPMessage` — read next message from client
- `send_to_client(msg: MCPMessage) -> None` — send message to client
- `send_to_backend(backend_name: str, msg: MCPMessage) -> MCPMessage` — forward to a specific backend and return its response
- `close() -> None` — clean up all connections and processes

No implementation here — only the interface. `StdioTransport` implements this in the next task.

---

### PROXY-04 — StdioTransport

Implement `proxy/stdio_transport.py`. This is the most complex task in the proxy module.

**`StdioTransport` extends `BaseTransport` and manages stdio communication.**

On initialization, for each backend in the config:
- Spawn the backend process using `asyncio.create_subprocess_exec` with `stdin=PIPE`, `stdout=PIPE`, `stderr=PIPE`
- Keep a reference to each process keyed by backend name
- Log spawning success or failure

**`receive_message()`** — read a line from `sys.stdin` (the client side), parse it as JSON-RPC, return an `MCPMessage`. This is how Claude's messages arrive.

**`send_to_client(msg)`** — serialize `MCPMessage` to JSON and write to `sys.stdout`. Flush after writing.

**`send_to_backend(backend_name, msg)`** — write the serialized message to the named backend's stdin, read a response line from its stdout, return a parsed `MCPMessage`. If the backend process has died, return an error `MCPMessage` instead of raising.

**`close()`** — terminate all spawned backend processes gracefully. Send SIGTERM first, wait briefly, then SIGKILL if still alive.

All reading and writing must be async. Do not use blocking I/O anywhere in this file.

---

### PROXY-05 — Router

Implement `proxy/router.py`.

**`Router` builds and maintains the tool-to-backend routing table.**

**`build(transport: BaseTransport, backends: list[BackendConfig]) -> None`** — for each backend, send a `tools/list` JSON-RPC request via `transport.send_to_backend()`, parse the response, extract tool names, store `tool_name → backend_name` mapping.

**`resolve(tool_name: str) -> str`** — return the backend name for a given tool name. Raise `ToolNotFoundError` if not found.

**`get_all_tools() -> dict[str, list[str]]`** — return `backend_name → [tool_names]` for all backends.

**Tool name collision:** if two backends expose a tool with the same name, log a warning and keep the first one. Do not raise an error.

**`ToolNotFoundError`** should be a custom exception defined in this file.

---

### PROXY-06 — Session and SessionManager

Implement `proxy/session.py`.

**`SessionEvent` dataclass** — one entry in the session trace:
- `timestamp` — datetime
- `direction` — Literal["request", "response"]
- `tool_name` — str
- `content` — dict (params for requests, result/error for responses)
- `flags` — list[str] (filled in by analysis pipeline later, empty for now)
- `decision` — Literal["pass", "block", "alert", "log"] (default: "pass")

**`SessionState` enum** — `NORMAL` and `ALERT`.

**`Session` class:**
- Fields: `session_id` (uuid), `created_at` (datetime), `state` (SessionState), `alert_triggered_at` (datetime or None), `events` (list[SessionEvent])
- `add_event(event: SessionEvent) -> None`
- `transition_to_alert() -> None` — set state to ALERT, record `alert_triggered_at`
- `check_and_reset_timeout(timeout_minutes: int) -> None` — if in ALERT and timeout elapsed, reset to NORMAL
- `get_window(size: int) -> list[SessionEvent]` — in NORMAL return last `size` events, in ALERT return all events since `alert_triggered_at`

**`SessionManager` class:**
- `create_session() -> Session`
- `get_session(session_id: str) -> Session | None`
- `get_or_create(session_id: str) -> Session`
- `close_session(session_id: str) -> None`
- `get_all_sessions() -> list[Session]` — needed by the API

---

### PROXY-07 — ProxyCore

Implement `proxy/core.py`.

**`ProxyCore` is the main orchestrator.** Ties together transport, router, and session manager. No analysis pipeline yet — just intercept and forward.

**`__init__(config: MCPSecConfig)`** — store config, instantiate `SessionManager`. Do not start yet.

**`async start() -> None`** — instantiate the correct transport based on config, spawn backends, call `router.build()`, then enter the main message loop.

**Main message loop:**
1. Call `transport.receive_message()` to get the next client message
2. If method is `initialize` — create a new session, forward to all backends, send response to client
3. If method is `tools/list` — return the aggregated tool list from all backends merged
4. If method is `tools/call` — resolve backend via `router.resolve(tool_name)`, create a `SessionEvent` for the request, add to session trace, forward to backend, create a `SessionEvent` for the response, add to trace, send response to client
5. Any other method — forward to the first available backend as fallback
6. On `ToolNotFoundError` — return a JSON-RPC error to the client

Leave a clearly commented placeholder between step 4 and "forward to backend":
```python
# TODO: run analysis pipeline here (regex, chain tracking, enforcement)
```

**`async stop() -> None`** — call `transport.close()`, clean up sessions.

**`is_running` property** — returns bool, needed by the API.

---

### PROXY-08 — API State and Server

Implement `api/state.py` and `api/server.py`.

**`api/state.py`** defines a single `AppState` class and a module-level `state` instance:

```python
class AppState:
    proxy: ProxyCore | None = None
    router: Router | None = None
    sessions: SessionManager | None = None
    config: MCPSecConfig | None = None

state = AppState()
```

This is imported by every API route to access live proxy internals. It is populated once in `main.py` after all modules are initialized.

**`api/server.py`** creates the FastAPI app:
- Create a `FastAPI` instance with title "MCPSec API" and version "0.1.0"
- Mount all route routers (one import per routes file)
- Include the WebSocket router
- Add CORS middleware allowing all origins (for dashboard development)
- Expose a `create_app() -> FastAPI` function
- Expose an `async start_api_server(app, host, port)` function that runs uvicorn programmatically without blocking the proxy's asyncio loop

---

### PROXY-09 — API Routes

Implement all route files under `api/routes/`. Each file is a FastAPI `APIRouter`. All routes read from `api/state.state` — they never import proxy internals directly.

**`events.py` — GET /api/events**
Query the session event trace. Support query params: `session_id` (filter by session), `tool_name`, `decision` (pass/block/alert/log), `limit` (default 100). Return a list of serialized `SessionEvent` objects.

**`sessions.py` — GET /api/sessions**
Return all active sessions from `state.sessions.get_all_sessions()`. Each entry includes: session_id, created_at, state (NORMAL/ALERT), event count, alert_triggered_at if in ALERT.

**`routing.py` — GET /api/routing-table**
Return `state.router.get_all_tools()` — the full `backend_name → [tool_names]` mapping.

**`analysis.py` — GET /api/toxic-flow**
Read and return `storage/results/toxic_flow_result.json`. Return 404 if the file does not exist yet (discovery hasn't run).

**`config.py` — GET /api/config and PUT /api/config**
GET returns the current `state.config` as JSON. PUT accepts a partial config update, merges with current config, writes back to `mcpsec-config.yaml`, updates `state.config`. Return the updated config.

**`proxy.py` — POST /api/proxy/start and POST /api/proxy/stop**
Start calls `state.proxy.start()` in a background asyncio task if proxy is not running. Stop calls `state.proxy.stop()`. Both return the current proxy status.

**`backends.py` — CRUD /api/backends**
GET returns the backend list from config plus live status (running/stopped) for each. POST adds a new backend to config and attempts to spawn it. PUT updates a backend config. DELETE stops and removes a backend. All changes persist to `mcpsec-config.yaml`.

**`rules.py` — CRUD /api/rules**
GET returns all enforcement rules from the rules file. POST adds a rule. PUT updates by rule id. DELETE removes by rule id. All changes persist to the rules file configured in `mcpsec-config.yaml`.

**`features.py` — PUT /api/features**
Accept a dict of feature flags (`embedding_filter`, `llm_evaluator`, `anomaly_detection`, `dashboard`). Update `state.config.features`, persist to `mcpsec-config.yaml`. Return updated feature flags.

**`rescan.py` — POST /api/rescan**
Trigger discovery re-scan in a background task. Returns immediately with `{"status": "rescan_started"}`. The background task re-runs tool discovery, updates `discovery_result.json`, re-runs toxic flow analyzer, updates `toxic_flow_result.json`, and calls `router.build()` to hot-reload the routing table.

---

### PROXY-10 — WebSocket Live Event Stream

Implement `api/websocket.py`.

**WebSocket endpoint at `/ws/events`.**

When a client connects:
- Register it in a connection set
- On disconnect, remove from set

When the proxy processes any tool call or response:
- The `ProxyCore` should call a `broadcast_event(event: SessionEvent)` function
- This function serializes the event and sends it to all connected WebSocket clients

**`broadcast_event(event: SessionEvent) -> None`** — serialize event to JSON dict, send to all active WebSocket connections. Handle disconnected clients gracefully (catch send errors, remove from set).

**`ProxyCore`** needs to be updated to call `broadcast_event` after each `SessionEvent` is created. Import from `api/websocket.py`.

The event JSON sent over WebSocket should match the same schema as `GET /api/events` — consistent format for the dashboard.

---

### PROXY-11 — Error Handling

Harden error handling across the proxy and API modules. No new files — modify existing ones.

**Proxy errors returned to the MCP client must be valid JSON-RPC error responses:**

```json
{
  "jsonrpc": "2.0",
  "id": "<original message id>",
  "error": {
    "code": -32000,
    "message": "MCPSec: <descriptive message>"
  }
}
```

**Cover the following proxy error cases:**
- Backend process fails to spawn — log error, exclude from routing table, continue with remaining backends
- Backend process dies during a tool call — return error to client, attempt to respawn, log the incident
- Backend returns malformed JSON — return error to client, log raw content
- Tool not found in routing table — return error with tool name mentioned
- No backends available — return error on any tool call
- Unhandled exception in main loop — log with full traceback, return error, continue loop (do not crash)

**API error responses must use standard HTTP status codes:**
- 404 when a resource does not exist (e.g., toxic-flow result not yet generated)
- 409 when an action conflicts with current state (e.g., start proxy when already running)
- 422 for validation errors (Pydantic handles this automatically)
- 500 for unexpected errors with a descriptive message

---

### PROXY-12 — Main Entry Point

Wire everything together in `main.py`.

**`main.py` should:**
1. Parse CLI argument for config file path (default: `mcpsec-config.yaml`)
2. Call `load_config(path)` — exit with clear message if config is invalid
3. Set up Python `logging` — log level from config or default INFO, structured format with timestamp
4. Instantiate `ProxyCore(config)` and `SessionManager`
5. Populate `api.state.state` with all module references
6. If `config.api.enabled` is true, call `start_api_server()` as an asyncio task
7. Call `asyncio.run(core.start())`
8. Handle `KeyboardInterrupt` gracefully — call `core.stop()` before exiting

**Logging format:**
```
2024-01-15 10:23:45 [INFO]    proxy.core    Session created: abc123
2024-01-15 10:23:45 [INFO]    proxy.router  Routing table built: 12 tools across 3 backends
2024-01-15 10:23:46 [WARNING] proxy.stdio   Backend 'email' process died, respawning...
2024-01-15 10:23:47 [INFO]    api.server    API server running at http://localhost:8080
```

---

### PROXY-13 — Smoke Test

Verify the full proxy + API works end-to-end.

**Setup:**
- Clone `appsecco/vulnerable-mcp-servers-lab`
- Pick the simplest available server (filesystem or echo server)
- Add it as a backend in `mcpsec-config.yaml`
- Set enforcement mode to `log`

**Proxy smoke test — verify manually:**
1. MCPSec starts, backends spawn, routing table is logged
2. Send a `tools/list` request — MCPSec returns the merged tool list
3. Send a `tools/call` for a valid tool — response returned correctly
4. Send a `tools/call` for a non-existent tool — MCP-compliant error returned
5. Kill a backend process manually — MCPSec logs the crash, returns error, does not crash

**API smoke test — use `http://localhost:8080/docs` (FastAPI auto-generated UI):**
1. GET /api/sessions — returns the active session
2. GET /api/routing-table — returns the correct tool mapping
3. GET /api/config — returns current config
4. PUT /api/features — toggle a feature flag, verify config file is updated
5. GET /api/events — returns the events from the tool calls made above
6. Connect a WebSocket client to `/ws/events`, make a tool call, verify the event arrives in real time

**Write results in `tests/integration/proxy_smoke_test.md`** — what worked, what failed, any unexpected behavior.

---

## Dependencies Between Tasks

```
PROXY-01 (skeleton)
    └── PROXY-02 (config)
            └── PROXY-03 (base transport + MCPMessage)
                    └── PROXY-04 (stdio transport)
                            ├── PROXY-05 (router)
                            └── PROXY-06 (session)
                                    └── PROXY-07 (proxy core)
                                            ├── PROXY-08 (API state + server)
                                            │       └── PROXY-09 (API routes)
                                            │               └── PROXY-10 (WebSocket)
                                            └── PROXY-11 (error handling)
                                                    └── PROXY-12 (main entry point)
                                                            └── PROXY-13 (smoke test)
```

---

## What Comes After This Module

Once PROXY-13 passes, the next modules plug in at the `# TODO: run analysis pipeline here` placeholder in `ProxyCore`:

- **Discovery module** — runs at startup, produces `discovery_result.json`
- **Toxic Flow Analyzer** — runs after discovery, produces `toxic_flow_result.json`
- **Regex Filter** — first stage of runtime pipeline
- **Chain Tracker** — second stage, reads `toxic_flow_result.json`
- **Enforcement Engine** — reads all pipeline flags, makes final decision
- **SQLite Logger** — persists every `SessionEvent` to the database
