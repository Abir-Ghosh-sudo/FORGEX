"""Base skill interface for FORGEX."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SkillContext:
    """Context passed to skill execution."""

    workspace: str
    task: str
    files: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillResult:
    """Result returned by a skill."""

    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    files_changed: list[str] = field(default_factory=list)


class Skill(ABC):
    """Abstract base class for FORGEX skills."""

    name: str = "skill"
    description: str = ""
    version: str = "1.0.0"

    @abstractmethod
    async def execute(self, context: SkillContext) -> SkillResult:
        """Execute the skill with the given context."""

    def validate_context(self, context: SkillContext) -> None:
        """Validate skill context before execution."""
        if not context.workspace:
            raise ValueError("Skill context requires a workspace path.")
        if not context.task:
            raise ValueError("Skill context requires a task description.")


__all__ = ["Skill", "SkillResult", "SkillContext"]
