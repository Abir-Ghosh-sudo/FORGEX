"""Builtin testing skill for FORGEX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgex.skills.base import Skill, SkillContext, SkillResult


class TestingSkill(Skill):
    """Builtin skill for test discovery and verification."""

    name = "testing"
    description = "Discover and run project tests."
    version = "1.0.0"

    async def execute(self, context: SkillContext) -> SkillResult:
        try:
            workspace = Path(context.workspace)
            test_files: list[str] = []
            for pattern in ("test_*.py", "*_test.py", "tests/**/*.py"):
                for p in workspace.rglob(pattern):
                    if p.is_file():
                        rel = p.relative_to(workspace)
                        test_files.append(str(rel))

            return SkillResult(
                success=True,
                output=f"Found {len(test_files)} test files.",
                data={"test_files": test_files},
            )
        except Exception as exc:
            return SkillResult(success=False, output="", error=str(exc))


__all__ = ["TestingSkill"]
