"""Change validation for FORGEX.

Validates file changes before and after edits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ChangeValidationResult:
    """Result of change validation."""

    valid: bool
    changes: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ChangeValidator:
    """Validates proposed and applied file changes."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def validate_change(
        self,
        file_path: str,
        old_content: str,
        new_content: str,
    ) -> ChangeValidationResult:
        """Validate a proposed file change."""
        result = ChangeValidationResult(valid=True)
        path = self.workspace / file_path

        if not old_content and not new_content:
            result.errors.append("Both old and new content are empty.")
            result.valid = False
            return result

        if old_content == new_content:
            result.warnings.append("Old and new content are identical.")
            return result

        # Check for path traversal
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(self.workspace.resolve())):
                result.errors.append(f"Path traversal detected: {file_path}")
                result.valid = False
        except Exception as exc:
            result.errors.append(f"Path resolution failed: {exc}")
            result.valid = False

        result.changes.append(
            {
                "file": file_path,
                "old_size": len(old_content),
                "new_size": len(new_content),
                "lines_added": max(0, len(new_content.splitlines()) - len(old_content.splitlines())),
            }
        )
        return result

    def validate_workspace_integrity(self) -> ChangeValidationResult:
        """Validate that workspace files are consistent."""
        result = ChangeValidationResult(valid=True)
        try:
            for p in self.workspace.rglob("*"):
                if p.is_file() and p.stat().st_size == 0:
                    result.warnings.append(f"Empty file: {p.relative_to(self.workspace)}")
        except Exception as exc:
            result.errors.append(f"Integrity check failed: {exc}")
            result.valid = False
        return result


__all__ = ["ChangeValidator", "ChangeValidationResult"]
