"""Shared FORGEX installation utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def check_python(min_version: tuple[int, int] = (3, 11)) -> bool:
    import sys

    return tuple(sys.version_info[:2]) >= min_version


def get_settings_template() -> str:
    return """# FORGEX configuration (.env)
FORGEX_APP__ENVIRONMENT=development
FORGEX_MODEL__PROVIDER=ollama
FORGEX_MODEL__MODEL_NAME=qwen2.5-coder:7b
FORGEX_MODEL__CONTEXT_WINDOW=8192
FORGEX_MODEL__MAX_OUTPUT_TOKENS=2048
FORGEX_RUNTIME__MAX_CONCURRENCY=1
FORGEX_SECURITY__REQUIRE_COMMAND_APPROVAL=true
FORGEX_STORAGE__DATA_DIR=~/.forgex/data
"""


def write_env_file(target: Path) -> None:
    target.write_text(get_settings_template(), encoding="utf-8")


__all__ = ["check_python", "get_settings_template", "write_env_file", "PROJECT_ROOT"]
