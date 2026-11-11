"""Skill system for FORGEX.

Provides skill interface, registry, loader, and builtin skill categories:
coding, debugging, testing, refactoring.
"""

from forgex.skills.base import Skill, SkillContext, SkillResult
from forgex.skills.registry import SkillRegistry

__all__ = ["Skill", "SkillResult", "SkillContext", "SkillRegistry"]
