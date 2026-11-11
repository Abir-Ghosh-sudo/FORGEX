"""Workspace filesystem protection and sensitive path detection."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


class ProtectionError(Exception):
    """Base exception for filesystem protection failures."""


class ProtectedPathError(ProtectionError):
    """Raised when an operation targets a protected path."""


@dataclass(frozen=True, slots=True)
class ProtectionResult:
    """Result of a filesystem protection check."""

    allowed: bool
    path: Path
    reason: str
    matched_pattern: str | None = None


class WorkspaceProtection:
    """Detect and protect sensitive workspace files and directories."""

    DEFAULT_PROTECTED_PATTERNS = (
        ".git",
        ".git/**",
        ".env",
        ".env.*",
        "**/.env",
        "**/.env.*",
        "*.pem",
        "**/*.pem",
        "*.key",
        "**/*.key",
        "id_rsa",
        "**/id_rsa",
        "id_ed25519",
        "**/id_ed25519",
        "*.p12",
        "**/*.p12",
        "*.pfx",
        "**/*.pfx",
        "credentials.json",
        "**/credentials.json",
        "secrets.json",
        "**/secrets.json",
    )

    def __init__(
        self,
        workspace: str | Path,
        *,
        protected_patterns: tuple[str, ...] | None = None,
        allow_read: bool = True,
    ) -> None:
        self._workspace = Path(workspace).expanduser().resolve(strict=True)

        if not self._workspace.is_dir():
            raise ValueError("Workspace must be an existing directory.")

        patterns = (
            self.DEFAULT_PROTECTED_PATTERNS if protected_patterns is None else protected_patterns
        )

        if isinstance(patterns, str):
            raise TypeError("protected_patterns must be a tuple of patterns.")

        if any(not isinstance(item, str) or not item.strip() for item in patterns):
            raise ValueError("Protected patterns must be non-empty strings.")

        self._patterns = list(dict.fromkeys(patterns))
        self._allow_read = allow_read
        self._lock = RLock()

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def protected_patterns(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._patterns)

    def add_pattern(self, pattern: str) -> None:
        """Register an additional protected path pattern."""

        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError("Pattern must be a non-empty string.")

        normalized = pattern.replace("\\", "/").strip()

        with self._lock:
            if normalized not in self._patterns:
                self._patterns.append(normalized)

    def remove_pattern(self, pattern: str) -> bool:
        """Remove a protected pattern."""

        with self._lock:
            try:
                self._patterns.remove(pattern)
                return True
            except ValueError:
                return False

    def inspect(
        self,
        path: str | Path,
        *,
        operation: str = "write",
    ) -> ProtectionResult:
        """Check whether a workspace path is protected."""

        candidate = Path(path).expanduser()

        if not candidate.is_absolute():
            candidate = self._workspace / candidate

        try:
            resolved = candidate.resolve(strict=False)
            relative = resolved.relative_to(self._workspace)
        except (OSError, ValueError):
            return ProtectionResult(
                allowed=False,
                path=candidate,
                reason="Path is outside the workspace or cannot be resolved.",
            )

        normalized = relative.as_posix()

        if operation not in {"read", "write", "delete", "move", "copy"}:
            return ProtectionResult(
                allowed=False,
                path=resolved,
                reason=f"Unsupported filesystem operation: {operation}",
            )

        with self._lock:
            patterns = tuple(self._patterns)

        for pattern in patterns:
            normalized_pattern = pattern.replace("\\", "/")

            if fnmatch.fnmatchcase(normalized, normalized_pattern) or self._matches_directory(
                normalized, normalized_pattern
            ):
                if operation == "read" and self._allow_read:
                    return ProtectionResult(
                        allowed=True,
                        path=resolved,
                        reason="Protected path is readable.",
                        matched_pattern=pattern,
                    )

                return ProtectionResult(
                    allowed=False,
                    path=resolved,
                    reason="Operation targets a protected workspace path.",
                    matched_pattern=pattern,
                )

        return ProtectionResult(
            allowed=True,
            path=resolved,
            reason="Path is not protected.",
        )

    def require_allowed(
        self,
        path: str | Path,
        *,
        operation: str = "write",
    ) -> Path:
        """Raise an exception when an operation is not permitted."""

        result = self.inspect(path, operation=operation)

        if not result.allowed:
            raise ProtectedPathError(result.reason)

        return result.path

    @staticmethod
    def _matches_directory(path: str, pattern: str) -> bool:
        """Match a protected directory and all its descendants."""

        if pattern.endswith("/**"):
            directory = pattern[:-3]
            return path == directory or path.startswith(directory + "/")

        return False
