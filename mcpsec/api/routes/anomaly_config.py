from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..state import state

router = APIRouter(prefix="/api/anomaly-config")


def _get_cfg() -> Any:
    if state.proxy and state.proxy.anomaly_detector:
        return state.proxy.anomaly_detector._config
    if state.config:
        return state.config.anomaly_detection
    return None


def _serialize(cfg: Any) -> dict[str, Any]:
    return {
        "enabled": cfg.enabled,
        "frequency": {
            "enabled": cfg.frequency.enabled,
            "max_per_minute": cfg.frequency.max_per_minute,
            "max_per_hour": cfg.frequency.max_per_hour,
        },
        "off_hours": {
            "enabled": cfg.off_hours.enabled,
            "start_hour": cfg.off_hours.start_hour,
            "end_hour": cfg.off_hours.end_hour,
        },
    }


@router.get("")
async def get_anomaly_config() -> dict[str, Any]:
    cfg = _get_cfg()
    if cfg is None:
        raise HTTPException(status_code=503, detail="Proxy not ready")
    return _serialize(cfg)


@router.put("")
async def update_anomaly_config(update: dict[str, Any]) -> dict[str, Any]:
    cfg = _get_cfg()
    if cfg is None:
        raise HTTPException(status_code=503, detail="Proxy not ready")

    if "enabled" in update:
        cfg.enabled = bool(update["enabled"])

    if "frequency" in update:
        freq = update["frequency"]
        if "enabled" in freq:
            cfg.frequency.enabled = bool(freq["enabled"])
        if "max_per_minute" in freq:
            v = int(freq["max_per_minute"])
            if v < 1:
                raise HTTPException(status_code=422, detail="max_per_minute must be >= 1")
            cfg.frequency.max_per_minute = v
        if "max_per_hour" in freq:
            v = int(freq["max_per_hour"])
            if v < 1:
                raise HTTPException(status_code=422, detail="max_per_hour must be >= 1")
            cfg.frequency.max_per_hour = v

    if "off_hours" in update:
        oh = update["off_hours"]
        if "enabled" in oh:
            cfg.off_hours.enabled = bool(oh["enabled"])
        if "start_hour" in oh:
            v = int(oh["start_hour"])
            if not (0 <= v <= 23):
                raise HTTPException(status_code=422, detail="start_hour must be 0–23")
            cfg.off_hours.start_hour = v
        if "end_hour" in oh:
            v = int(oh["end_hour"])
            if not (0 <= v <= 23):
                raise HTTPException(status_code=422, detail="end_hour must be 0–23")
            cfg.off_hours.end_hour = v

    return _serialize(cfg)
