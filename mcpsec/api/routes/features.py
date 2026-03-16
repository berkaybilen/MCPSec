from __future__ import annotations

import os
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from ..state import state

router = APIRouter(prefix="/api")

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "mcpsec-config.yaml")


@router.put("/features")
async def update_features(flags: dict[str, bool]) -> dict[str, Any]:
    if state.config is None:
        raise HTTPException(status_code=503, detail="Config not loaded.")

    current_flags = state.config.features.model_dump()
    invalid = [k for k in flags if k not in current_flags]
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown feature flags: {invalid}")

    current_flags.update(flags)
    from config import FeaturesConfig  # noqa: PLC0415

    state.config.features = FeaturesConfig.model_validate(current_flags)

    path = os.path.abspath(_CONFIG_PATH)
    with open(path, "w") as f:
        yaml.dump(state.config.model_dump(), f, default_flow_style=False)

    return state.config.features.model_dump()
