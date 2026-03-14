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


class MCPSecConfig(BaseModel):
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    api: ApiConfig = Field(default_factory=ApiConfig)
    backends: list[BackendConfig] = Field(default_factory=list)
    enforcement: EnforcementConfig = Field(default_factory=EnforcementConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)


def load_config(path: str) -> MCPSecConfig:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return MCPSecConfig.model_validate(data or {})
