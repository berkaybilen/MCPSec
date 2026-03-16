from __future__ import annotations

import os
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from ..state import state

router = APIRouter(prefix="/api")

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "mcpsec-config.yaml")


@router.get("/config")
async def get_config() -> Any:
    if state.config is None:
        raise HTTPException(status_code=503, detail="Config not loaded.")
    return state.config.model_dump()


@router.put("/config")
async def update_config(update: dict[str, Any]) -> Any:
    if state.config is None:
        raise HTTPException(status_code=503, detail="Config not loaded.")

    current = state.config.model_dump()
    _deep_merge(current, update)

    from config import MCPSecConfig  # noqa: PLC0415

    try:
        new_config = MCPSecConfig.model_validate(current)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    path = os.path.abspath(_CONFIG_PATH)
    with open(path, "w") as f:
        yaml.dump(current, f, default_flow_style=False)

    state.config = new_config
    return new_config.model_dump()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
