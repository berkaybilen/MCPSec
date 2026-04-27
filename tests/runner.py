#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.harness import list_demo_scenarios, run_scenario
from tests.harness import reset_runtime_state
from tests.scenario_assertions import assert_scenario_result


def _match_scenarios(selector: str | None) -> list[Path]:
    scenarios = list_demo_scenarios()
    if selector is None:
        return scenarios
    return [path for path in scenarios if path.stem.startswith(selector)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local MCPSec demo scenarios")
    parser.add_argument("scenario", nargs="?", help="Scenario prefix, e.g. DEMO-001")
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Clear stored demo runtime data before executing scenarios",
    )
    args = parser.parse_args()

    scenario_paths = _match_scenarios(args.scenario)
    if not scenario_paths:
        print(f"No scenarios matched: {args.scenario}")
        sys.exit(1)

    if args.reset_db:
        reset_runtime_state()

    failures = 0
    for scenario_path in scenario_paths:
        result = run_scenario(scenario_path)
        spec = result["spec"]
        session = result["session"]
        events = result["events"]
        try:
            assert_scenario_result(result)
            passed = True
        except AssertionError as exc:
            passed = False
            failure_message = str(exc)
        status = "PASS" if passed else "FAIL"

        print(f"{spec['id']} {spec['name']} ... {status}")
        print(f"  session:  {session['session_id']} state={session['state']} events={len(events)}")
        for event in events:
            print(
                f"  {event['direction']:8} tool={event['tool_name']:<20} "
                f"decision={event['decision']:<5} flags={','.join(event['flags']) or '-'}"
            )
        if not passed:
            print(f"  reason:   {failure_message}")
            failures += 1

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
