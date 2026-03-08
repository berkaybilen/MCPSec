from __future__ import annotations

import os
import uuid
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from api.state import state

router = APIRouter(prefix="/api/rules")


def _rules_path() -> str:
    if state.config and state.config.enforcement.rules_file:
        rules_file = state.config.enforcement.rules_file
        if not os.path.isabs(rules_file):
            base = os.path.join(os.path.dirname(__file__), "..", "..")
            rules_file = os.path.abspath(os.path.join(base, rules_file))
        return rules_file
    return os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "rules.yaml")
    )


def _load_rules() -> list[dict[str, Any]]:
    path = _rules_path()
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, list) else []


def _save_rules(rules: list[dict[str, Any]]) -> None:
    path = _rules_path()
    with open(path, "w") as f:
        yaml.dump(rules, f, default_flow_style=False)


@router.get("")
async def list_rules() -> list[dict[str, Any]]:
    return _load_rules()


@router.post("")
async def add_rule(rule: dict[str, Any]) -> dict[str, Any]:
    rules = _load_rules()
    if "id" not in rule:
        rule["id"] = str(uuid.uuid4())
    rules.append(rule)
    _save_rules(rules)
    return rule


@router.put("/{rule_id}")
async def update_rule(rule_id: str, update: dict[str, Any]) -> dict[str, Any]:
    rules = _load_rules()
    for i, rule in enumerate(rules):
        if str(rule.get("id")) == rule_id:
            rules[i].update(update)
            _save_rules(rules)
            return rules[i]
    raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str) -> dict[str, Any]:
    rules = _load_rules()
    for i, rule in enumerate(rules):
        if str(rule.get("id")) == rule_id:
            rules.pop(i)
            _save_rules(rules)
            return {"deleted": rule_id}
    raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found.")
