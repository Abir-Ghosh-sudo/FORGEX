"""Skill registry for FORGEX.

Registers, discovers, and manages skill lifecycle with permission-aware execution.
"""

from __future__ import annotations

import logging
from typing import Any

from forgex.skills.base import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry for FORGEX skills."""

    def __init__(self) -> None:
        self._skills: dict[str, type[Skill]] = {}
        self._instances: dict[str, Skill] = {}

    def register(self, skill_class: type[Skill]) -> None:
        """Register a skill class."""
        if not issubclass(skill_class, Skill):
            raise TypeError(f"{skill_class} is not a Skill subclass.")
        name = getattr(skill_class, "name", None) or skill_class.__name__
        self._skills[name] = skill_class
        logger.info("Skill registered: %s", name)

    def unregister(self, name: str) -> bool:
        """Unregister a skill by name."""
        if name in self._skills:
            del self._skills[name]
            self._instances.pop(name, None)
            return True
        return False

    def list_skills(self) -> list[str]:
        """List registered skill names."""
        return sorted(self._skills.keys())

    def get(self, name: str) -> type[Skill] | None:
        """Get a skill class by name."""
        return self._skills.get(name)

    def create_instance(self, name: str) -> Skill:
        """Create an instance of a registered skill."""
        skill_class = self.get(name)
        if skill_class is None:
            raise ValueError(f"Skill not registered: {name}")
        if name not in self._instances:
            self._instances[name] = skill_class()
        return self._instances[name]

    async def execute(
        self,
        name: str,
        context: SkillContext,
    ) -> SkillResult:
        """Execute a registered skill by name."""
        skill = self.create_instance(name)
        skill.validate_context(context)
        try:
            return await skill.execute(context)
        except Exception as exc:
            logger.exception("Skill %s execution failed.", name)
            return SkillResult(
                success=False,
                output="",
                error=str(exc),
            )


__all__ = ["SkillRegistry"]
