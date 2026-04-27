from __future__ import annotations

import pytest

from .harness import list_demo_scenarios, read_sessions, reset_runtime_state, run_scenario
from .scenario_assertions import assert_scenario_result


SCENARIO_PATHS = list_demo_scenarios()


@pytest.fixture(autouse=True)
def clean_runtime_state():
    reset_runtime_state()
    yield
    reset_runtime_state()


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=lambda path: path.stem)
def test_demo_scenarios(scenario_path) -> None:
    result = run_scenario(scenario_path)
    assert_scenario_result(result)


def test_demo_history_accumulates_across_runs() -> None:
    first = run_scenario(SCENARIO_PATHS[0])
    second = run_scenario(SCENARIO_PATHS[1])

    sessions = read_sessions(limit=10)
    session_ids = {session["session_id"] for session in sessions}

    assert first["session"]["session_id"] in session_ids
    assert second["session"]["session_id"] in session_ids
    assert len(session_ids) >= 2
