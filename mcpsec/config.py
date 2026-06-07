from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, Field


class ProxyConfig(BaseModel):
    transport: Literal["stdio", "http"] = "stdio"
    port: int = 3001


class ApiConfig(BaseModel):
    port: int = 8080
    enabled: bool = True


class BackendConfig(BaseModel):
    name: str
    transport: Literal["stdio", "http"] = "stdio"
    # stdio
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    # http
    url: str | None = None


class EnforcementConfig(BaseModel):
    default_mode: Literal["block", "alert", "log"] = "alert"
    rules_file: str = "rules.yaml"


class SessionConfig(BaseModel):
    alert_timeout_minutes: int = 30
    sliding_window_size: int = 10


class StateMachineConfig(BaseModel):
    enabled: bool = True
    sanitizer_tools: list[str] = Field(default_factory=list)


class FeaturesConfig(BaseModel):
    embedding_filter: bool = False
    llm_evaluator: bool = False
    anomaly_detection: bool = True
    dashboard: bool = True


class DiscoveryConfig(BaseModel):
    schema_probing: bool = True
    hidden_tool_detection: bool = True
    tech_fingerprinting: bool = True
    change_detection: bool = True
    probing_timeout_ms: int = 5000


class ToxicFlowThresholds(BaseModel):
    u: int = 5
    s: int = 4
    e: int = 4


class ToxicFlowSemanticConfig(BaseModel):
    enabled: bool = True
    model: str = "all-MiniLM-L6-v2"
    confirm_threshold: float = 0.75
    support_threshold: float = 0.55
    contradict_threshold: float = 0.35
    borderline_window: int = 1


class ToxicFlowConfig(BaseModel):
    enabled: bool = True
    result_path: str = "storage/results/toxic_flow_result.json"
    thresholds: ToxicFlowThresholds = Field(default_factory=ToxicFlowThresholds)
    suppressor_multiplier: float = 0.5
    compound_bonus: int = 4
    semantic: ToxicFlowSemanticConfig = Field(default_factory=ToxicFlowSemanticConfig)


class ChainCombinationPolicyUSE(BaseModel):
    on_u_seen: Literal["LOG", "ALERT", "BLOCK"] = "LOG"
    on_us_seen: Literal["LOG", "ALERT", "BLOCK"] = "ALERT"
    on_complete: Literal["LOG", "ALERT", "BLOCK"] = "BLOCK"


class ChainCombinationPolicy(BaseModel):
    on_first: Literal["LOG", "ALERT", "BLOCK"] = "LOG"
    on_complete: Literal["LOG", "ALERT", "BLOCK"] = "BLOCK"


class ChainPolicies(BaseModel):
    USE: ChainCombinationPolicyUSE = Field(default_factory=ChainCombinationPolicyUSE)
    SE: ChainCombinationPolicy = Field(default_factory=ChainCombinationPolicy)
    US: ChainCombinationPolicy = Field(
        default_factory=lambda: ChainCombinationPolicy(on_first="LOG", on_complete="ALERT")
    )
    UE: ChainCombinationPolicy = Field(
        default_factory=lambda: ChainCombinationPolicy(on_first="LOG", on_complete="ALERT")
    )


class ChainTrackingConfig(BaseModel):
    enabled: bool = True
    normal_window_size: int = 10
    alert_timeout_minutes: int | None = None
    data_flow_tracking: bool = False
    policies: ChainPolicies = Field(default_factory=ChainPolicies)
    default_policy: Literal["LOG", "ALERT", "BLOCK"] = "LOG"
    result_path: str = "storage/results/toxic_flow_result.json"


class AnomalyFrequencyConfig(BaseModel):
    enabled: bool = True
    max_per_minute: int = 30
    max_per_hour: int = 500


class AnomalyOffHoursConfig(BaseModel):
    enabled: bool = True
    start_hour: int = 0   # inclusive, 0–23
    end_hour: int = 6     # exclusive, 0–23


class AnomalyLearningConfig(BaseModel):
    enabled: bool = True
    alpha: float = 0.1              # EMA weight of new sample
    warmup_hours: float = 24.0      # collect-only period before z-scoring
    min_data_points: int = 100      # per-tool samples required before z-scoring
    outlier_z: float = 5.0          # |z| above this is excluded from EMA updates


class AnomalyZThresholds(BaseModel):
    low: float = 2.0      # 2 <= |z| < 3  -> LOW
    medium: float = 3.0   # 3 <= |z| < 5  -> MEDIUM
    high: float = 5.0     # |z| >= 5      -> HIGH


class AnomalyMultipliers(BaseModel):
    no_label: float = 0.5
    single_label: float = 1.0
    dual_combination: float = 1.5
    lethal_trifecta: float = 2.0


class AnomalyToxicFlowIntegrationConfig(BaseModel):
    enabled: bool = True
    multipliers: AnomalyMultipliers = Field(default_factory=AnomalyMultipliers)


class AnomalySeverityActions(BaseModel):
    low: Literal["pass", "log", "alert", "block"] = "log"
    medium: Literal["pass", "log", "alert", "block"] = "alert"
    high: Literal["pass", "log", "alert", "block"] = "alert"
    critical: Literal["pass", "log", "alert", "block"] = "block"


class AnomalyDetectionConfig(BaseModel):
    enabled: bool = True
    frequency: AnomalyFrequencyConfig = Field(default_factory=AnomalyFrequencyConfig)
    off_hours: AnomalyOffHoursConfig = Field(default_factory=AnomalyOffHoursConfig)
    learning: AnomalyLearningConfig = Field(default_factory=AnomalyLearningConfig)
    z_thresholds: AnomalyZThresholds = Field(default_factory=AnomalyZThresholds)
    toxic_flow_integration: AnomalyToxicFlowIntegrationConfig = Field(
        default_factory=AnomalyToxicFlowIntegrationConfig
    )
    severity_actions: AnomalySeverityActions = Field(default_factory=AnomalySeverityActions)


class MCPSecConfig(BaseModel):
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    backends: list[BackendConfig] = Field(default_factory=list)
    enforcement: EnforcementConfig = Field(default_factory=EnforcementConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    state_machine: StateMachineConfig = Field(default_factory=StateMachineConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    toxic_flow: ToxicFlowConfig = Field(default_factory=ToxicFlowConfig)
    chain_tracking: ChainTrackingConfig = Field(default_factory=ChainTrackingConfig)
    anomaly_detection: AnomalyDetectionConfig = Field(default_factory=AnomalyDetectionConfig)


def load_config(path: str) -> MCPSecConfig:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return MCPSecConfig.model_validate(data or {})
