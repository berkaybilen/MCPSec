from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api")

_TOXIC_FLOW_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "storage", "results", "toxic_flow_result.json"
)


@router.get("/toxic-flow")
async def get_toxic_flow() -> Any:
    path = os.path.abspath(_TOXIC_FLOW_PATH)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Toxic flow result not yet generated.")
    with open(path) as f:
        return json.load(f)
