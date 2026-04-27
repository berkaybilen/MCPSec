from __future__ import annotations

import pytest

from .harness import list_demo_scenarios, run_scenario
from .scenario_assertions import assert_scenario_result


SCENARIO_PATHS = list_demo_scenarios()


@pytest.mark.parametrize("scenario_path", SCENARIO_PATHS, ids=lambda path: path.stem)
def test_demo_scenarios(scenario_path) -> None:
    result = run_scenario(scenario_path)
    assert_scenario_result(result)
