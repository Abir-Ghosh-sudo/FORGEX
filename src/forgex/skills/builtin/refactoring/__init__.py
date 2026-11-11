"""Builtin refactoring skill for FORGEX."""

from __future__ import annotations

from pathlib import Path

from forgex.skills.base import Skill, SkillContext, SkillResult


class RefactoringSkill(Skill):
    """Builtin skill for code refactoring suggestions."""

    name = "refactoring"
    description = "Analyze code and suggest refactoring improvements."
    version = "1.0.0"

    async def execute(self, context: SkillContext) -> SkillResult:
        try:
            workspace = Path(context.workspace)
            suggestions: list[str] = []

            for rel in context.files:
                target = workspace / rel
                if target.exists() and target.is_file():
                    try:
                        text = target.read_text(encoding="utf-8", errors="replace")
                        lines = text.splitlines()
                        if len(lines) > 200:
                            suggestions.append(f"{rel}: file exceeds 200 lines, consider splitting")
                        for i, line in enumerate(lines, 1):
                            if len(line) > 120:
                                suggestions.append(f"{rel}:{i}: line exceeds 120 characters")
                    except Exception:
                        suggestions.append(f"{rel}: could not analyze")

            return SkillResult(
                success=True,
                output="\n".join(suggestions) or "No refactoring suggestions.",
                data={"suggestions": suggestions},
            )
        except Exception as exc:
            return SkillResult(success=False, output="", error=str(exc))


__all__ = ["RefactoringSkill"]
