from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Warning:
    backend: str
    tool: str
    type: str
    message: str

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "tool": self.tool,
            "type": self.type,
            "message": self.message,
        }


def validate_tool(tool_name: str, schema: dict, backend_name: str) -> list[Warning]:
    """Check a tool schema for completeness and return any warnings."""
    warnings: list[Warning] = []

    description = schema.get("description", "")
    if not description or not description.strip():
        warnings.append(Warning(
            backend=backend_name,
            tool=tool_name,
            type="missing_description",
            message=f"Tool '{tool_name}' has no description — Toxic Flow labeling will be inaccurate",
        ))

    input_schema = schema.get("inputSchema")
    if input_schema is None:
        warnings.append(Warning(
            backend=backend_name,
            tool=tool_name,
            type="missing_input_schema",
            message=f"Tool '{tool_name}' has no inputSchema field",
        ))
    else:
        properties: dict = input_schema.get("properties", {}) or {}
        required: list = input_schema.get("required", []) or []

        for param_name, param_schema in properties.items():
            if not isinstance(param_schema, dict):
                continue
            if "type" not in param_schema:
                warnings.append(Warning(
                    backend=backend_name,
                    tool=tool_name,
                    type="missing_parameter_type",
                    message=f"Tool '{tool_name}' parameter '{param_name}' has no type field",
                ))
            if not param_schema.get("description", "").strip():
                warnings.append(Warning(
                    backend=backend_name,
                    tool=tool_name,
                    type="missing_parameter_description",
                    message=f"Tool '{tool_name}' parameter '{param_name}' has no description",
                ))

        for req_field in required:
            if req_field not in properties:
                warnings.append(Warning(
                    backend=backend_name,
                    tool=tool_name,
                    type="undefined_required_fields",
                    message=(
                        f"Tool '{tool_name}' required field '{req_field}' "
                        f"is not defined in properties"
                    ),
                ))

    return warnings
