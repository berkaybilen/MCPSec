from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

ROOT = Path(__file__).resolve().parent.parent.parent.parent
PYTHON = ROOT / ".venv" / "bin" / "python"
DEMO_CONFIG = ROOT / "mcpsec-demo-config.yaml"
DB_PATH = ROOT / "mcpsec" / "storage" / "mcpsec.db"
TOXIC_FLOW_RESULT = ROOT / "mcpsec" / "storage" / "results" / "toxic_flow_result.json"
LOG_FILE = ROOT / "mcpsec-demo.log"
SCENARIOS_DIR = ROOT / "tests" / "scenarios"

router = APIRouter(prefix="/api/scenarios")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenario-runner")
_run_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------

def _load_scenarios() -> list[dict[str, Any]]:
    result = []
    for path in sorted(SCENARIOS_DIR.glob("DEMO-*.yaml")):
        with path.open() as f:
            spec = yaml.safe_load(f)
        spec["_path"] = str(path)
        result.append(spec)
    return result


# ---------------------------------------------------------------------------
# Inline runner (mirrors tests/harness.py — avoids sys.path dependency)
# ---------------------------------------------------------------------------

def _read_json_line(stream: Any) -> dict[str, Any]:
    line = stream.readline()
    if not line:
        raise RuntimeError("Proxy closed stdout unexpectedly.")
    return json.loads(line)


def _send_msg(proc: Any, payload: dict) -> dict:
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()
    return _read_json_line(proc.stdout)


def _send_notif(proc: Any, payload: dict) -> None:
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _wait_for_analysis(timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if TOXIC_FLOW_RESULT.exists():
            try:
                data = json.loads(TOXIC_FLOW_RESULT.read_text())
                if data.get("tools"):
                    return
            except Exception:
                pass
        time.sleep(0.1)


def _read_latest_session() -> dict[str, Any]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    if row is None:
        raise RuntimeError("No session rows written.")
    return dict(row)


def _read_events(session_id: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id = ? ORDER BY id ASC", (session_id,)
    ).fetchall()
    conn.close()
    events = []
    for row in rows:
        ev = dict(row)
        ev["flags"] = json.loads(ev["flags"])
        ev["content"] = json.loads(ev["content"])
        events.append(ev)
    return events


def _extract_text(response: dict) -> str:
    result = response.get("result") or {}
    chunks = result.get("content", [])
    return "\n".join(c.get("text", "") for c in chunks if c.get("type") == "text")


def _check_step(step: dict, response: dict) -> tuple[bool, str | None]:
    expect = step.get("expect_response", {})
    if "error_contains" in expect:
        error = response.get("error")
        if error is None:
            return False, f"Expected an error response but got none for '{step['tool']}'"
        if expect["error_contains"] not in error.get("message", ""):
            return False, f"Error message doesn't contain '{expect['error_contains']}'"
        return True, None
    if response.get("error"):
        return False, f"Unexpected error: {response['error'].get('message', '')}"
    text = _extract_text(response)
    if "text_contains" in expect and expect["text_contains"] not in text:
        return False, f"Response missing '{expect['text_contains']}'"
    if "text_not_contains" in expect and expect["text_not_contains"] in text:
        return False, f"Response unexpectedly contains '{expect['text_not_contains']}'"
    return True, None


def _find_event(events: list[dict], tool: str, direction: str) -> dict | None:
    for ev in reversed(events):
        if ev["tool_name"] == tool and ev["direction"] == direction:
            return ev
    return None


def _run_scenario_sync(scenario_path: str) -> dict[str, Any]:
    spec = yaml.safe_load(Path(scenario_path).read_text())
    start = time.time()

    proc = subprocess.Popen(
        [str(PYTHON), "-m", "mcpsec", "--config", str(DEMO_CONFIG),
         "--no-api", "--log-file", str(LOG_FILE)],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    responses: list[dict] = []
    run_error: str | None = None

    try:
        responses.append(_send_msg(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "scenario-runner", "version": "0.1.0"}},
        }))
        _send_notif(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        responses.append(_send_msg(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        _wait_for_analysis()

        for i, step in enumerate(spec.get("steps", [])):
            responses.append(_send_msg(proc, {
                "jsonrpc": "2.0", "id": 10 + i, "method": "tools/call",
                "params": {"name": step["tool"], "arguments": step.get("arguments", {})},
            }))
    except Exception as exc:
        run_error = str(exc)
    finally:
        if proc.stdin:
            proc.stdin.close()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=3)

    duration_ms = int((time.time() - start) * 1000)

    if run_error:
        return {"passed": False, "error": run_error, "duration_ms": duration_ms,
                "step_results": [], "events": [], "session": None}

    try:
        session = _read_latest_session()
        events = _read_events(session["session_id"])
    except Exception as exc:
        return {"passed": False, "error": str(exc), "duration_ms": duration_ms,
                "step_results": [], "events": [], "session": None}

    step_responses = responses[2:]  # skip initialize + tools/list
    step_results = []
    passed = True
    error: str | None = None

    for step, resp in zip(spec.get("steps", []), step_responses):
        ok, err = _check_step(step, resp)
        if not ok:
            passed = False
            if error is None:
                error = err
        step_results.append({
            "tool": step["tool"],
            "arguments": step.get("arguments", {}),
            "expect_response": step.get("expect_response", {}),
            "passed": ok,
            "error": err,
        })

    expect = spec.get("expect", {})
    if "session_state" in expect and session["state"] != expect["session_state"]:
        passed = False
        error = error or f"Session state: expected {expect['session_state']}, got {session['state']}"

    for ev_expect in expect.get("events", []):
        ev = _find_event(events, ev_expect["tool"], ev_expect["direction"])
        if ev is None:
            passed = False
            error = error or f"Event not found: {ev_expect['tool']} {ev_expect['direction']}"
            continue
        if "decision" in ev_expect and ev["decision"] != ev_expect["decision"]:
            passed = False
            error = error or f"{ev_expect['tool']}: expected decision={ev_expect['decision']}, got {ev['decision']}"
        for flag in ev_expect.get("flags_include", []):
            if flag not in ev["flags"]:
                passed = False
                error = error or f"{ev_expect['tool']}: missing flag '{flag}'"

    return {
        "passed": passed,
        "error": error,
        "duration_ms": duration_ms,
        "step_results": step_results,
        "events": events,
        "session": session,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
async def list_scenarios() -> list[dict[str, Any]]:
    try:
        return [{k: v for k, v in s.items() if k != "_path"} for s in _load_scenarios()]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{scenario_id}/run")
async def run_scenario(scenario_id: str) -> dict[str, Any]:
    scenarios = _load_scenarios()
    scenario = next((s for s in scenarios if s.get("id") == scenario_id), None)
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Scenario {scenario_id!r} not found")

    if _run_lock.locked():
        raise HTTPException(status_code=409, detail="Another scenario is already running")

    async with _run_lock:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            _executor, lambda: _run_scenario_sync(scenario["_path"])
        )

    return {"id": scenario_id, "name": scenario.get("name", ""), **result}
