"""Enforcement engine — per-rule mode overrides, ALERT escalation, redact support."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

import yaml

logger = logging.getLogger("enforcement.engine")

_PRIORITY: dict[str, int] = {"block": 4, "alert": 3, "log": 2, "pass": 1}
_ESCALATION: dict[str, str] = {"log": "alert", "alert": "block", "block": "block", "pass": "alert"}


@dataclass
class EnforcementResult:
    decision: Literal["pass", "block", "alert", "log"]
    redact: bool = False
    matched_rules: list[str] = field(default_factory=list)

    @property
    def is_blocking(self) -> bool:
        return self.decision == "block"


def _load_rules(rules_file: str) -> list[dict[str, Any]]:
    """Load rules from YAML file. Returns empty list if file missing."""
    if not rules_file or not os.path.exists(rules_file):
        return []
    try:
        with open(rules_file) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("Failed to load rules file %s: %s", rules_file, exc)
        return []


def _merge(current: str, candidate: str) -> str:
    """Return the more restrictive of two decisions."""
    return current if _PRIORITY.get(current, 0) >= _PRIORITY.get(candidate, 0) else candidate


def decide(
    flags: list[str],
    global_mode: str,
    *,
    rules_file: str = "",
    session_state: str = "NORMAL",
) -> EnforcementResult:
    """
    Decide enforcement action for a set of detected flags.

    Priority order:
      1. Per-rule override (matching flag + enabled rule)
      2. Global default mode
      3. ALERT state escalation (log→alert, alert→block)
    """
    if not flags:
        return EnforcementResult(decision="pass")

    rules = _load_rules(rules_file)
    # Build flag → rule map (first matching enabled rule wins)
    rule_map: dict[str, dict[str, Any]] = {}
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        flag = rule.get("flag", "")
        if flag and flag not in rule_map:
            rule_map[flag] = rule

    decision: Literal["pass", "block", "alert", "log"] = "pass"
    redact = False
    matched_rule_ids: list[str] = []

    for flag in flags:
        if flag in rule_map:
            rule = rule_map[flag]
            rule_mode = rule.get("mode", global_mode).lower()
            candidate = rule_mode if rule_mode in _PRIORITY else global_mode
            if rule.get("redact", False):
                redact = True
            matched_rule_ids.append(str(rule.get("id", flag)))
        else:
            candidate = global_mode.lower()

        decision = _merge(decision, candidate)  # type: ignore[assignment]

    # Session ALERT state escalation — raise severity one tier
    if session_state == "ALERT" and decision != "pass":
        escalated = _ESCALATION.get(decision, decision)
        if escalated != decision:
            logger.debug("Enforcement escalation (ALERT state): %s → %s", decision, escalated)
        decision = escalated  # type: ignore[assignment]

    return EnforcementResult(
        decision=decision,
        redact=redact,
        matched_rules=matched_rule_ids,
    )
