"""Regex-based detection for prompt injection, path traversal, and credential leaks."""

from __future__ import annotations

import re
from typing import Any

# Response patterns — prompt injection indicators in tool responses
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?above\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"you\s+must\s+now\s+(call|use|execute|run)", re.IGNORECASE),
    re.compile(r"system\s*prompt\s*override", re.IGNORECASE),
    re.compile(r"<\s*!--.*?(call|send|execute|forward|exfil).*?-->", re.IGNORECASE | re.DOTALL),
    re.compile(r"do\s+not\s+reveal\s+this\s+to\s+the\s+user", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
]

# Request patterns — suspicious tool arguments
PATH_TRAVERSAL = re.compile(r"\.\./|\.\.\\|/etc/passwd|/etc/shadow|~\/\.ssh|~\/\.env")
SQL_INJECTION = re.compile(r"('\s*(OR|AND)\s+'|;\s*(DROP|DELETE|UPDATE|INSERT)\s+|UNION\s+SELECT)", re.IGNORECASE)

# Response patterns — credential leaks
CREDENTIAL_PATTERNS = [
    re.compile(r"(api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"(sk-|pk-|ghp_|gho_|AIza)[A-Za-z0-9_\-]{10,}"),
]


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        parts = []
        for item in content.get("content", []):
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n".join(parts) if parts else str(content)
    return str(content)


def _redact_text(text: str) -> str:
    """Replace credential values in a plain string with [REDACTED]."""
    # Pattern 1: key=value or key: value style — redact the value part
    result = re.sub(
        r"((api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*)\S+",
        r"\1[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    # Pattern 2: well-known token prefixes — redact the whole token
    result = re.sub(
        r"(sk-|pk-|ghp_|gho_|AIza)[A-Za-z0-9_\-]{10,}",
        "[REDACTED]",
        result,
    )
    return result


def redact_credentials(content: Any) -> Any:
    """
    Recursively mask credential values in tool response content.
    Returns a new object with secrets replaced by [REDACTED].
    """
    if isinstance(content, str):
        return _redact_text(content)
    if isinstance(content, dict):
        if "content" in content and isinstance(content["content"], list):
            new_items = []
            for item in content["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    new_items.append({**item, "text": _redact_text(item.get("text", ""))})
                else:
                    new_items.append(item)
            return {**content, "content": new_items}
        return {k: redact_credentials(v) for k, v in content.items()}
    if isinstance(content, list):
        return [redact_credentials(item) for item in content]
    return content


def analyze_request(tool_name: str, params: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    text = str(params)
    if PATH_TRAVERSAL.search(text):
        flags.append("path_traversal")
    if SQL_INJECTION.search(text):
        flags.append("sql_injection")
    return flags


def analyze_response(tool_name: str, content: Any) -> list[str]:
    flags: list[str] = []
    text = _text_from_content(content)
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            flags.append("injection_detected")
            break
    for pattern in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            flags.append("credential_leak")
            break
    return flags
