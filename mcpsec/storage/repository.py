"""storage/repository.py — Persistent read/write for sessions and events."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Any

from .db import get_connection, init_db

logger = logging.getLogger("storage.repository")


class EventRepository:
    """Thread-safe SQLite-backed store for sessions and events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        init_db()

    # ------------------------------------------------------------------
    # Writes (called from proxy — hot path, keep fast)
    # ------------------------------------------------------------------

    def upsert_session(self, session_id: str, created_at: str, state: str, event_count: int) -> None:
        with self._lock:
            conn = get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO sessions (session_id, created_at, state, event_count)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        state       = excluded.state,
                        event_count = excluded.event_count
                """, (session_id, created_at, state, event_count))
            conn.close()

    def close_session(self, session_id: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            conn = get_connection()
            with conn:
                conn.execute(
                    "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
                    (now, session_id),
                )
            conn.close()

    def save_event(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            conn = get_connection()
            with conn:
                conn.execute("""
                    INSERT INTO events (session_id, timestamp, direction, tool_name, flags, decision, content)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    event["timestamp"],
                    event["direction"],
                    event["tool_name"],
                    json.dumps(event.get("flags", [])),
                    event.get("decision", "pass"),
                    json.dumps(event.get("content", {})),
                ))
                conn.execute("""
                    UPDATE sessions SET event_count = event_count + 1 WHERE session_id = ?
                """, (session_id,))
            conn.close()

    # ------------------------------------------------------------------
    # Reads (called from API — can be slightly slower)
    # ------------------------------------------------------------------

    def get_sessions(
        self,
        include_closed: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        conn = get_connection()
        query = "SELECT * FROM sessions"
        if not include_closed:
            query += " WHERE ended_at IS NULL"
        query += " ORDER BY created_at DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_events(
        self,
        session_id: str | None = None,
        tool_name: str | None = None,
        decision: str | None = None,
        flags_contain: str | None = None,
        since: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id)
        if tool_name:
            clauses.append("tool_name = ?")
            params.append(tool_name)
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        if flags_contain:
            clauses.append("flags LIKE ?")
            params.append(f"%{flags_contain}%")
        if since:
            clauses.append("timestamp >= ?")
            params.append(since)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = get_connection()
        rows = conn.execute(query, params).fetchall()
        conn.close()

        results = []
        for r in rows:
            d = dict(r)
            d["flags"] = json.loads(d["flags"])
            d["content"] = json.loads(d["content"])
            results.append(d)
        return results

    def save_routing_table(self, table: dict[str, str]) -> None:
        """Persist tool→backend mapping. Replaces previous snapshot."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            conn = get_connection()
            with conn:
                conn.execute("DELETE FROM routing_table")
                conn.executemany(
                    "INSERT INTO routing_table (tool_name, backend_name, updated_at) VALUES (?, ?, ?)",
                    [(tool, backend, now) for tool, backend in table.items()],
                )
            conn.close()

    def get_routing_table(self) -> dict[str, Any]:
        conn = get_connection()
        rows = conn.execute(
            "SELECT tool_name, backend_name, updated_at FROM routing_table ORDER BY tool_name"
        ).fetchall()
        conn.close()
        if not rows:
            return {"status": "no data yet", "tool_to_backend": {}, "backend_to_tools": {}}

        tool_to_backend: dict[str, str] = {}
        backend_to_tools: dict[str, list[str]] = {}
        updated_at = None
        for r in rows:
            tool_to_backend[r["tool_name"]] = r["backend_name"]
            backend_to_tools.setdefault(r["backend_name"], []).append(r["tool_name"])
            updated_at = r["updated_at"]

        return {
            "status": "ready",
            "updated_at": updated_at,
            "tool_to_backend": tool_to_backend,
            "backend_to_tools": backend_to_tools,
        }

    def get_stats(self) -> dict[str, Any]:
        conn = get_connection()
        sessions_total = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        events_total   = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        flagged        = conn.execute("SELECT COUNT(*) FROM events WHERE flags != '[]'").fetchone()[0]
        blocked        = conn.execute("SELECT COUNT(*) FROM events WHERE decision = 'block'").fetchone()[0]
        alerted        = conn.execute("SELECT COUNT(*) FROM events WHERE decision = 'alert'").fetchone()[0]
        conn.close()
        return {
            "sessions_total": sessions_total,
            "events_total":   events_total,
            "flagged_events": flagged,
            "blocked":        blocked,
            "alerted":        alerted,
        }
