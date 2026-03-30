"""Enforcement engine — decides block/alert/log based on detected flags and config mode."""

from __future__ import annotations

from typing import Literal


def decide(flags: list[str], mode: str) -> Literal["pass", "block", "alert", "log"]:
    if not flags:
        return "pass"
    if mode == "block":
        return "block"
    if mode == "alert":
        return "alert"
    return "log"
