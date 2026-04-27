from __future__ import annotations

from fastapi.testclient import TestClient

from mcpsec.api.server import create_app
from mcpsec.api.state import state
from mcpsec.config import load_config

from .harness import DEMO_CONFIG, list_demo_scenarios, reset_runtime_state, run_scenario


def setup_function() -> None:
    reset_runtime_state()
    state.proxy = None
    state.router = None
    state.sessions = None
    state.config = None


def teardown_function() -> None:
    reset_runtime_state()
    state.proxy = None
    state.router = None
    state.sessions = None
    state.config = None


def test_chain_state_is_available_for_persisted_sessions() -> None:
    scenario = next(path for path in list_demo_scenarios() if path.stem.startswith("DEMO-005"))
    result = run_scenario(scenario)

    state.config = load_config(str(DEMO_CONFIG))
    client = TestClient(create_app())

    response = client.get(f"/api/sessions/{result['session']['session_id']}/chain-state")
    assert response.status_code == 200

    payload = response.json()
    assert payload["session_id"] == result["session"]["session_id"]
    assert payload["current_chain_state"] == "USE_COMPLETE"
    assert any(combo["combination"] == "USE" for combo in payload["active_combinations"])
    assert len(payload["window_entries"]) >= 3


def test_reset_runtime_endpoint_clears_persisted_history() -> None:
    run_scenario(list_demo_scenarios()[0])
    run_scenario(list_demo_scenarios()[1])

    state.config = load_config(str(DEMO_CONFIG))
    client = TestClient(create_app())

    before = client.get("/api/sessions")
    assert before.status_code == 200
    assert len(before.json()) >= 2

    reset = client.post("/api/backends/reset-runtime")
    assert reset.status_code == 200
    reset_payload = reset.json()
    assert reset_payload["status"] == "ok"
    assert reset_payload["deleted_sessions"] >= 2
    assert reset_payload["deleted_events"] >= 4

    after_sessions = client.get("/api/sessions")
    after_events = client.get("/api/events")
    assert after_sessions.status_code == 200
    assert after_events.status_code == 200
    assert after_sessions.json() == []
    assert after_events.json() == []


def test_sessions_endpoint_exposes_display_state_from_event_history() -> None:
    run_scenario(next(path for path in list_demo_scenarios() if path.stem.startswith("DEMO-002")))
    blocked = run_scenario(next(path for path in list_demo_scenarios() if path.stem.startswith("DEMO-005")))

    state.config = load_config(str(DEMO_CONFIG))
    client = TestClient(create_app())

    response = client.get("/api/sessions")
    assert response.status_code == 200
    sessions = response.json()

    blocked_session = next(
        session for session in sessions if session["session_id"] == blocked["session"]["session_id"]
    )
    assert blocked_session["state"] == "NORMAL"
    assert blocked_session["display_state"] == "BLOCK"

    assert any(session["display_state"] == "ALERT" for session in sessions)
