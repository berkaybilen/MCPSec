# MCPSec — Project Scope & Architecture

## What Is MCPSec?

MCPSec is a transparent security proxy that sits between an MCP client (e.g., Claude Desktop, Claude Code) and one or more MCP servers. It intercepts every tool call and response, analyzes them for security threats, and enforces configurable policies — all without requiring any changes to the client or servers.

It also exposes a REST API and WebSocket feed so a dashboard (or any external tool) can observe and control the proxy in real time.

---

## Problem It Solves

MCP lets LLM agents autonomously call external tools (filesystems, databases, email) from a single user prompt without further approval. An attacker can embed hidden instructions in sources the agent reads (websites, documents, files), causing it to:

- Read sensitive files and email them to the attacker (prompt injection → data exfiltration)
- Read config files containing API keys and leak them (credential theft)
- Execute a full attack chain when Untrusted Input (U) + Sensitive Access (S) + External Output (E) tools coexist in one agent (Lethal Trifecta)

---

## How It Works — Three Phases

**Phase 1 — Startup (runs once):**
Query all backend servers for tool schemas → label tools by risk category (U/S/E) → identify dangerous tool combinations → build routing table.

**Phase 2 — Runtime (every message):**
Every tool call and response passes through a layered analysis pipeline (regex → chain tracking → embedding). Block or alert on threats.

**Phase 3 — Background (continuous):**
Monitor behavioral patterns, detect deviations from normal usage via anomaly detection.

---

## System Topology

```
Claude Desktop / Claude Code
        │
        │  (sees one MCP server)
        ▼
  ┌─────────────────────────────────────────┐
  │              MCPSec Process             │
  │                                         │
  │   Proxy Core  ←──→  REST API + WS       │
  │       │               (port 8080)       │
  │       │                                 │
  │   SQLite DB  ←─────────────────────┐   │
  │   JSON results                      │   │
  └───────┼─────────────────────────────┼───┘
          │                             │
          │  stdio / HTTP               │ reads
          ▼                             │
  Filesystem MCP Server          Dashboard (browser)
  Database MCP Server            or any HTTP client
  Email MCP Server
```

The proxy and the REST API run in the same process using asyncio. They share in-memory state directly — session objects, routing table, config. The dashboard connects to the API and does not need to be running for the proxy to work.

---

## Module Overview

```
Startup:
  Tool Discovery ──→ discovery_result.json ──→ Toxic Flow Analyzer ──→ toxic_flow_result.json

Runtime:
  tool call arrives
      │
      ▼
  Session Trace
      │
      ▼
  Regex Filter ──→ Chain Tracking ──→ Embedding Filter (M2) ──→ Enforcement Engine
                                                                        │
                                                              forward / block / alert
  response arrives
      │
      ▼
  Session Trace
      │
      ▼
  Regex Filter (credentials + injection) ──→ Embedding Filter (M2) ──→ Enforcement Engine

Background:
  Anomaly Detection reads SQLite log + toxic_flow_result.json

API (parallel, same process):
  REST API serves config, sessions, events, routing table, toxic flow results
  WebSocket streams live events to connected clients
```

---

## Directory Structure

```
mcpsec/
├── main.py                        # Entry point — starts proxy + API in same asyncio loop
├── config.py                      # Loads and validates mcpsec-config.yaml
├── mcpsec-config.yaml             # Single config file for all settings
│
├── proxy/
│   ├── base.py                    # BaseTransport abstract class + MCPMessage dataclass
│   ├── stdio_transport.py         # stdio implementation (spawn + stdin/stdout)
│   ├── http_transport.py          # HTTP/SSE implementation (M2)
│   ├── router.py                  # Routing table: tool name → backend server
│   ├── session.py                 # Session class + SessionManager + state machine
│   └── core.py                    # ProxyCore orchestrator
│
├── discovery/
│   ├── discovery.py               # Sends tools/list to each backend, collects schemas
│   ├── tokenizer.py               # snake_case/camelCase parsing, stop word removal
│   └── validator.py               # Schema completeness checks, flags missing fields
│
├── analysis/
│   ├── toxic_flow.py              # Tool labeling (U/S/E) + risk matrix + dangerous paths
│   ├── regex_filter.py            # Attack patterns (requests) + credential patterns (responses)
│   ├── chain_tracker.py           # Subsequence matching against dangerous paths
│   ├── embedding_filter.py        # Semantic similarity — all-MiniLM-L6-v2 (M2)
│   └── anomaly.py                 # Predefined rules + adaptive learning (M2/M3)
│
├── enforcement/
│   └── engine.py                  # Reads pipeline flags, decides block/alert/log
│
├── storage/
│   ├── repository.py              # EventRepository abstract class + SQLiteEventRepository
│   ├── db.py                      # DB connection, schema creation, raw SQL helpers
│   └── results/                   # JSON output files written at startup
│       ├── discovery_result.json
│       └── toxic_flow_result.json
│
├── api/
│   ├── server.py                  # FastAPI app, mounts all routers, starts uvicorn
│   ├── state.py                   # Shared in-memory state (proxy, router, sessions, repo)
│   ├── websocket.py               # WebSocket endpoint — streams live events
│   └── routes/
│       ├── events.py              # GET /api/events
│       ├── sessions.py            # GET /api/sessions
│       ├── routing.py             # GET /api/routing-table
│       ├── analysis.py            # GET /api/toxic-flow
│       ├── config.py              # GET /api/config, PUT /api/config
│       ├── proxy.py               # POST /api/proxy/start, POST /api/proxy/stop
│       ├── backends.py            # CRUD /api/backends
│       ├── rules.py               # CRUD /api/rules
│       ├── features.py            # PUT /api/features
│       └── rescan.py              # POST /api/rescan
│
└── tests/
    ├── unit/
    └── integration/
```

---

## Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Language | Python 3.11+ | Official MCP SDK is Python, asyncio native |
| Async runtime | asyncio | Proxy and API both run in same event loop |
| MCP protocol | `mcp` (official Python SDK) | Handles JSON-RPC parsing |
| HTTP / API | FastAPI + uvicorn | Async, WebSocket support, auto docs at /docs |
| HTTP client | httpx | Async HTTP for HTTP transport (M2) |
| Config | PyYAML + Pydantic v2 | Type-safe config validation |
| Database | SQLite via raw `sqlite3` | Zero setup, single file |
| Embedding | `sentence-transformers` | all-MiniLM-L6-v2, runs locally (M2) |
| Testing | pytest + pytest-asyncio | Async test support |

> **Database note:** All modules use an `EventRepository` interface, not SQLite directly. Migrating to PostgreSQL later is a single-file change.

> **API note:** FastAPI auto-generates interactive docs at `http://localhost:8080/docs`. Useful for testing all endpoints before the frontend exists.

---

## REST API Reference

| Method | Path | Description |
|---|---|---|
| GET | /api/events | Query event log with filters (session, tool, decision, time range) |
| GET | /api/sessions | All active sessions with state (NORMAL/ALERT) and event count |
| GET | /api/routing-table | Current tool → backend mapping |
| GET | /api/toxic-flow | Full toxic flow analysis result |
| GET | /api/config | Current config |
| PUT | /api/config | Update config + hot-reload affected modules |
| POST | /api/proxy/start | Start the proxy if stopped |
| POST | /api/proxy/stop | Stop the proxy (API stays running) |
| GET | /api/backends | Backend list with status (running / stopped) |
| POST | /api/backends | Add a new backend |
| PUT | /api/backends/{name} | Update a backend config |
| DELETE | /api/backends/{name} | Remove a backend |
| GET | /api/rules | All enforcement rules |
| POST | /api/rules | Add a new rule |
| PUT | /api/rules/{id} | Update a rule |
| DELETE | /api/rules/{id} | Delete a rule |
| PUT | /api/features | Toggle features on/off |
| POST | /api/rescan | Trigger re-discovery + re-run toxic flow analyzer |
| WS | /ws/events | WebSocket — streams live events as they happen |

---

## Key Design Patterns

### 1 — Pipeline Pattern (AnalysisContext)

Every message creates an `AnalysisContext` object that passes through each filter. Filters add flags but never make blocking decisions. The enforcement engine decides at the end.

```python
context = AnalysisContext(message=msg, session=session)
context = await regex_filter.analyze(context)
context = await chain_tracker.analyze(context)
context = await embedding_filter.analyze(context)   # M2
decision = enforcement_engine.decide(context)
```

### 2 — BaseTransport Abstraction

All transport-specific code is behind a `BaseTransport` interface. Everything above never knows if it is stdio or HTTP mode.

```python
class BaseTransport(ABC):
    async def receive_message(self) -> MCPMessage: ...
    async def send_to_client(self, msg: MCPMessage) -> None: ...
    async def send_to_backend(self, backend: str, msg: MCPMessage) -> MCPMessage: ...
    async def close(self) -> None: ...
```

### 3 — Repository Pattern (Database)

No module imports `sqlite3` directly. All DB access goes through `EventRepository`.

```python
class EventRepository(ABC):
    async def save_event(self, event: Event) -> None: ...
    async def get_session_events(self, session_id: str) -> list[Event]: ...

class SQLiteEventRepository(EventRepository): ...   # current
class PostgreSQLEventRepository(EventRepository): ...  # future
```

### 4 — Shared API State

API routes access live proxy internals through a single `api/state.py` module that holds references to the proxy core, router, session manager, and repository. Set once at startup, read by all routes.

```python
# api/state.py
class AppState:
    proxy: ProxyCore | None = None
    router: Router | None = None
    sessions: SessionManager | None = None
    repository: EventRepository | None = None
    config: MCPSecConfig | None = None

state = AppState()
```

### 5 — Session State Machine

Each session has two states: NORMAL and ALERT. ALERT is triggered when a prompt injection pattern is detected in a tool response. In ALERT state, severity escalates one tier and chain tracking window expands to all events since the alert. ALERT resets after configurable timeout (default: 30 minutes).

---

## Configuration File Structure

```yaml
proxy:
  transport: stdio
  port: 3001

api:
  port: 8080
  enabled: true

backends:
  - name: filesystem
    transport: stdio
    command: "npx"
    args: ["@modelcontextprotocol/server-filesystem", "/tmp"]
  - name: email
    transport: stdio
    command: "python"
    args: ["email_server.py"]

enforcement:
  default_mode: alert
  rules_file: rules.yaml

session:
  alert_timeout_minutes: 30
  sliding_window_size: 10

features:
  embedding_filter: false
  llm_evaluator: false
  anomaly_detection: true
  dashboard: true
```

---

## Milestone Scope

| Milestone | Weeks | Focus |
|---|---|---|
| M1 | 1–4 | Proxy core (stdio), session management, discovery, toxic flow, regex filter, chain tracking, enforcement, SQLite logger, predefined anomaly rules, REST API + WebSocket |
| M2 | 5–8 | Embedding filter, HTTP transport, cross-server chain tracking, parameter/time anomaly, toxic flow severity integration |
| M3 | 9–12 | Data flow tracking, adaptive learning, LLM evaluator, multi-user, dashboard frontend |

---

## Data Flow Between Modules

```
discovery_result.json
    written by: Tool Discovery (startup)
    read by:    Toxic Flow Analyzer, Router, Chain Tracker, Anomaly Detection, GET /api/routing-table

toxic_flow_result.json
    written by: Toxic Flow Analyzer (startup)
    read by:    Chain Tracker, Anomaly Detection, GET /api/toxic-flow

SQLite event log
    written by: Repository (every event, runtime)
    read by:    Anomaly Detection, GET /api/events, WS /ws/events
```

---

## Test Environment

Integration tests run against `appsecco/vulnerable-mcp-servers-lab` — intentionally vulnerable MCP servers covering prompt injection, credential leakage, and path traversal scenarios.

FastAPI auto-generates interactive API docs at `http://localhost:8080/docs` — useful for manually testing all API endpoints before the frontend exists.
