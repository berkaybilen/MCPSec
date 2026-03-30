#!/usr/bin/env python3
"""MCPSec test runner — runs security scenarios and verifies detection."""

from __future__ import annotations

import argparse
import glob
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = ROOT / "mcpsec-test.log"
SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"

FLAG_PATTERN = re.compile(
    r"(REQUEST|RESPONSE)\s+flags=\[([^\]]*)\]\s+decision=(\w+)\s+tool=(\S+)"
)


def find_scenario(scenario_id: str) -> Path:
    matches = glob.glob(str(SCENARIOS_DIR / f"{scenario_id}*.yaml"))
    if not matches:
        print(f"Scenario not found: {scenario_id}")
        sys.exit(1)
    return Path(matches[0])


def parse_flags_from_log() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    results = []
    for line in LOG_FILE.read_text().splitlines():
        m = FLAG_PATTERN.search(line)
        if m:
            flags = [f.strip().strip("'\"") for f in m.group(2).split(",") if f.strip()]
            results.append({
                "direction": m.group(1).lower(),
                "flags": flags,
                "decision": m.group(3),
                "tool": m.group(4),
            })
    return results


def run_scenario(scenario_path: Path) -> bool:
    spec = yaml.safe_load(scenario_path.read_text())

    LOG_FILE.write_text("")

    # TODO: Gmail MCP opens its own HTTP server on port 3000. If a previous
    # run's process is still alive, the new one crashes with EADDRINUSE.
    # This is a workaround — proper fix is preventing zombie processes upstream.
    subprocess.run("lsof -ti :3000 | xargs kill 2>/dev/null", shell=True)

    mcp_config = ROOT / spec.get("mcp_config", "test-mcp-config.json")
    cmd = [
        "claude",
        "-p", spec["prompt"],
        "--mcp-config", str(mcp_config),
        "--output-format", "json",
        "--max-turns", str(spec.get("max_turns", 25)),
    ]

    timeout = spec.get("timeout", 120)
    try:
        subprocess.run(cmd, cwd=str(ROOT), timeout=timeout, capture_output=True)
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after {timeout}s")
        return False

    detections = parse_flags_from_log()
    found_flags = set()
    for d in detections:
        found_flags.update(d["flags"])

    expected_flags = set(spec.get("expect", {}).get("flags", []))
    passed = expected_flags.issubset(found_flags)

    status = "PASS" if passed else "FAIL"
    print(f"{spec['id']} {spec['name']} ... {status}")
    print(f"  expected: {', '.join(sorted(expected_flags))}")
    if detections:
        for d in detections:
            print(f"  found:    {', '.join(d['flags'])} (decision={d['decision']}, tool={d['tool']})")
    else:
        print("  found:    (none)")

    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description="MCPSec security test runner")
    parser.add_argument("scenario", help="Scenario ID (e.g. PI-001)")
    args = parser.parse_args()

    scenario_path = find_scenario(args.scenario)
    passed = run_scenario(scenario_path)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
