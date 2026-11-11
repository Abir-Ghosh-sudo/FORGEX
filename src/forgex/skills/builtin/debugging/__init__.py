"""Builtin debugging skill for FORGEX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgex.skills.base import Skill, SkillContext, SkillResult


class DebuggingSkill(Skill):
    """Builtin skill for debugging assistance."""

    name = "debugging"
    description = "Analyze errors and suggest fixes for debugging."
    version = "1.0.0"

    async def execute(self, context: SkillContext) -> SkillResult:
        try:
            workspace = Path(context.workspace)
            findings: list[str] = []
            files_checked: list[str] = []

            for rel in context.files:
                target = workspace / rel
                if target.exists() and target.is_file():
                    files_checked.append(rel)
                    try:
                        text = target.read_text(encoding="utf-8", errors="replace")
                        if "TODO" in text or "FIXME" in text:
                            findings.append(f"{rel}: contains TODO/FIXME markers")
                        if "except Exception:" in text or "except:" in text:
                            findings.append(f"{rel}: bare exception handler detected")
                    except Exception:
                        findings.append(f"{rel}: could not read file")

            return SkillResult(
                success=True,
                output="\n".join(findings) or "No debugging issues found.",
                data={"files_checked": files_checked, "findings": findings},
            )
        except Exception as exc:
            return SkillResult(success=False, output="", error=str(exc))


__all__ = ["DebuggingSkill"]
