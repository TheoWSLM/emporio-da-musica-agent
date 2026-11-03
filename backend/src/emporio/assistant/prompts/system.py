"""The agent's static system prompt (prompts/system.md) with its confidential canary token."""

from __future__ import annotations

import secrets
from pathlib import Path

_TEMPLATE = (Path(__file__).with_name("system.md")).read_text(encoding="utf-8")


def new_canary() -> str:
    return f"EMP-{secrets.token_hex(6)}"


def system_prompt(canary: str) -> str:
    return _TEMPLATE.replace("{canary}", canary)
