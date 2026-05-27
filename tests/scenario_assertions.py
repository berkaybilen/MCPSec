from __future__ import annotations


def find_event(events: list[dict], tool_name: str, direction: str) -> dict:
    for event in reversed(events):
        if event["tool_name"] == tool_name and event["direction"] == direction:
            return event
    raise AssertionError(f"Event not found: tool={tool_name} direction={direction}")


def extract_text(response: dict) -> str:
    result = response.get("result") or {}
    chunks = result.get("content", [])
    if not chunks:
        return ""
    return "\n".join(chunk.get("text", "") for chunk in chunks if chunk.get("type") == "text")


def assert_response(step: dict, response: dict) -> None:
    expect = step.get("expect_response", {})
    if "error_contains" in expect:
        error = response.get("error")
        assert error is not None, f"Expected an error response for step {step['tool']}"
        assert expect["error_contains"] in error.get("message", "")
    else:
        assert response.get("error") is None, f"Unexpected error for step {step['tool']}: {response}"

    text = extract_text(response)
    if "text_contains" in expect:
        assert expect["text_contains"] in text
    if "text_not_contains" in expect:
        assert expect["text_not_contains"] not in text


def assert_events(expectations: list[dict], events: list[dict]) -> None:
    for expectation in expectations:
        event = find_event(events, expectation["tool"], expectation["direction"])
        if "decision" in expectation:
            assert event["decision"] == expectation["decision"]
        for flag in expectation.get("flags_include", []):
            assert flag in event["flags"], f"Missing flag '{flag}' in {event['tool_name']} {event['direction']}"


def assert_scenario_result(result: dict) -> None:
    spec = result["spec"]
    responses = result["responses"][2:]
    events = result["events"]
    session = result["session"]

    for step, response in zip(spec.get("steps", []), responses, strict=True):
        assert_response(step, response)

    expect = spec.get("expect", {})
    if "session_state" in expect:
        assert session["state"] == expect["session_state"]
    assert_events(expect.get("events", []), events)
