from __future__ import annotations

import json
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
DEMO_CONFIG = ROOT / "mcpsec-demo-config.yaml"
DB_PATH = ROOT / "mcpsec" / "storage" / "mcpsec.db"
DISCOVERY_RESULT = ROOT / "mcpsec" / "storage" / "results" / "discovery_result.json"
TOXIC_FLOW_RESULT = ROOT / "mcpsec" / "storage" / "results" / "toxic_flow_result.json"
LOG_FILE = ROOT / "mcpsec-demo.log"
SCENARIOS_DIR = ROOT / "tests" / "scenarios"


def cleanup_artifacts() -> None:
    for path in (DB_PATH, DISCOVERY_RESULT, TOXIC_FLOW_RESULT, LOG_FILE):
        if path.exists():
            path.unlink()


def _read_json_line(stream: Any) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise RuntimeError("Proxy process closed stdout unexpectedly.")
    return json.loads(line)


def _send_message(process: subprocess.Popen[str], payload: dict[str, Any]) -> dict[str, Any]:
    assert process.stdin is not None
    assert process.stdout is not None
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()
    return _read_json_line(process.stdout)


def _send_notification(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()


def wait_for_analysis(timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if TOXIC_FLOW_RESULT.exists():
            with TOXIC_FLOW_RESULT.open() as f:
                data = json.load(f)
            if data.get("tools"):
                return
        time.sleep(0.1)
    raise RuntimeError("Timed out waiting for toxic flow analysis to finish.")


def read_latest_session() -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        raise RuntimeError("No session rows were written.")
    return dict(row)


def read_events(session_id: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()

    events: list[dict[str, Any]] = []
    for row in rows:
        event = dict(row)
        event["flags"] = json.loads(event["flags"])
        event["content"] = json.loads(event["content"])
        events.append(event)
    return events


def load_scenario(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def list_demo_scenarios() -> list[Path]:
    return sorted(SCENARIOS_DIR.glob("DEMO-*.yaml"))


def run_scenario(path: Path) -> dict[str, Any]:
    spec = load_scenario(path)
    cleanup_artifacts()

    process = subprocess.Popen(
        [
            str(PYTHON),
            "-m",
            "mcpsec",
            "--config",
            str(DEMO_CONFIG),
            "--no-api",
            "--log-file",
            str(LOG_FILE),
        ],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    responses: list[dict[str, Any]] = []

    try:
        initialize = _send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "demo-runner", "version": "0.1.0"},
                },
            },
        )
        responses.append(initialize)

        _send_notification(
            process,
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )

        tool_list = _send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        responses.append(tool_list)
        wait_for_analysis()

        next_id = 10
        for step in spec.get("steps", []):
            response = _send_message(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": next_id,
                    "method": "tools/call",
                    "params": {
                        "name": step["tool"],
                        "arguments": step.get("arguments", {}),
                    },
                },
            )
            responses.append(response)
            next_id += 1
    finally:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=3)

    session = read_latest_session()
    events = read_events(session["session_id"])

    return {
        "spec": spec,
        "responses": responses,
        "session": session,
        "events": events,
    }
