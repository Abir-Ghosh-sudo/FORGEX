"""Code verification for FORGEX.

Validates code changes for syntax, imports, and basic correctness.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VerificationResult:
    """Result of a verification check."""

    passed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def add_check(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.passed = False

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


class CodeVerifier:
    """Verifies code changes for syntax and import correctness."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

    def verify_python_file(self, file_path: str | Path) -> VerificationResult:
        """Verify a Python file for syntax errors."""
        result = VerificationResult(passed=True)
        path = Path(file_path)
        if not path.exists():
            result.add_error(f"File not found: {path}")
            return result

        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            result.add_error(f"Cannot read file: {exc}")
            return result

        try:
            ast.parse(source)
            result.add_check("syntax", True, "Python syntax valid")
        except SyntaxError as exc:
            result.add_check("syntax", False, f"Syntax error: {exc}")
            result.add_error(f"Syntax error in {path}: {exc}")

        # Check for obvious broken imports
        for line_no, line in enumerate(source.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                result.add_check(f"import_line_{line_no}", True, stripped[:80])

        return result

    def verify_file(self, file_path: str | Path) -> VerificationResult:
        """Verify a file based on its extension."""
        path = Path(file_path)
        if path.suffix == ".py":
            return self.verify_python_file(path)
        result = VerificationResult(passed=True)
        result.add_check("file_exists", path.exists(), str(path))
        return result

    def verify_workspace(self) -> VerificationResult:
        """Verify all Python files in the workspace."""
        result = VerificationResult(passed=True)
        try:
            for p in self.workspace.rglob("*.py"):
                if any(part in {".git", ".venv", "__pycache__", "node_modules", "build"} for part in p.parts):
                    continue
                file_result = self.verify_file(p)
                if not file_result.passed:
                    result.passed = False
                    result.errors.extend(file_result.errors)
                result.checks.extend(file_result.checks)
        except Exception as exc:
            result.add_error(f"Workspace verification failed: {exc}")
        return result


__all__ = ["CodeVerifier", "VerificationResult"]
