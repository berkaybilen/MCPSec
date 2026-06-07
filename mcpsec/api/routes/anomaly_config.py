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
        "learning": {
            "enabled": cfg.learning.enabled,
            "alpha": cfg.learning.alpha,
            "warmup_hours": cfg.learning.warmup_hours,
            "min_data_points": cfg.learning.min_data_points,
            "outlier_z": cfg.learning.outlier_z,
        },
        "z_thresholds": {
            "low": cfg.z_thresholds.low,
            "medium": cfg.z_thresholds.medium,
            "high": cfg.z_thresholds.high,
        },
        "toxic_flow_integration": {
            "enabled": cfg.toxic_flow_integration.enabled,
            "multipliers": cfg.toxic_flow_integration.multipliers.model_dump(),
        },
        "severity_actions": cfg.severity_actions.model_dump(),
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

    if "learning" in update:
        lr = update["learning"]
        if "enabled" in lr:
            cfg.learning.enabled = bool(lr["enabled"])
        if "alpha" in lr:
            v = float(lr["alpha"])
            if not (0.0 < v <= 1.0):
                raise HTTPException(status_code=422, detail="alpha must be in (0, 1]")
            cfg.learning.alpha = v
        if "warmup_hours" in lr:
            v = float(lr["warmup_hours"])
            if v < 0:
                raise HTTPException(status_code=422, detail="warmup_hours must be >= 0")
            cfg.learning.warmup_hours = v
        if "min_data_points" in lr:
            v = int(lr["min_data_points"])
            if v < 1:
                raise HTTPException(status_code=422, detail="min_data_points must be >= 1")
            cfg.learning.min_data_points = v
        if "outlier_z" in lr:
            v = float(lr["outlier_z"])
            if v <= 0:
                raise HTTPException(status_code=422, detail="outlier_z must be > 0")
            cfg.learning.outlier_z = v

    if "z_thresholds" in update:
        zt = update["z_thresholds"]
        for key in ("low", "medium", "high"):
            if key in zt:
                v = float(zt[key])
                if v <= 0:
                    raise HTTPException(status_code=422, detail=f"z_thresholds.{key} must be > 0")
                setattr(cfg.z_thresholds, key, v)
        if not (cfg.z_thresholds.low < cfg.z_thresholds.medium < cfg.z_thresholds.high):
            raise HTTPException(status_code=422, detail="z_thresholds must satisfy low < medium < high")

    if "toxic_flow_integration" in update:
        tf = update["toxic_flow_integration"]
        if "enabled" in tf:
            cfg.toxic_flow_integration.enabled = bool(tf["enabled"])
        if "multipliers" in tf:
            for key in ("no_label", "single_label", "dual_combination", "lethal_trifecta"):
                if key in tf["multipliers"]:
                    v = float(tf["multipliers"][key])
                    if v <= 0:
                        raise HTTPException(status_code=422, detail=f"multipliers.{key} must be > 0")
                    setattr(cfg.toxic_flow_integration.multipliers, key, v)

    if "severity_actions" in update:
        sa = update["severity_actions"]
        for key in ("low", "medium", "high", "critical"):
            if key in sa:
                v = str(sa[key]).lower()
                if v not in ("pass", "log", "alert", "block"):
                    raise HTTPException(
                        status_code=422,
                        detail=f"severity_actions.{key} must be one of pass/log/alert/block",
                    )
                setattr(cfg.severity_actions, key, v)

    return _serialize(cfg)
