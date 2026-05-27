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


def load_config(path: str) -> MCPSecConfig:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return MCPSecConfig.model_validate(data or {})
