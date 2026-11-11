
"""Workspace-safe file metadata inspection."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver
from forgex.tools.filesystem.protection import WorkspaceProtection


class MetadataInspectionError(Exception):
    """Raised when file metadata cannot be inspected."""


@dataclass(frozen=True, slots=True)
class FileMetadata:
    """Metadata describing a workspace filesystem entry."""

    name: str
    path: Path
    relative_path: str
    entry_type: str
    size_bytes: int
    extension: str | None
    created_at: datetime
    modified_at: datetime
    accessed_at: datetime
    mode: int
    readable: bool
    writable: bool
    executable: bool
    is_hidden: bool
    is_symlink: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": str(self.path),
            "relative_path": self.relative_path,
            "entry_type": self.entry_type,
            "size_bytes": self.size_bytes,
            "extension": self.extension,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "mode": self.mode,
            "readable": self.readable,
            "writable": self.writable,
            "executable": self.executable,
            "is_hidden": self.is_hidden,
            "is_symlink": self.is_symlink,
        }


class FileMetadataInspector:
    """Inspect metadata for files and directories inside a workspace."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        protection: WorkspaceProtection | None = None,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be WorkspacePathResolver.")

        if protection is not None:
            if not isinstance(protection, WorkspaceProtection):
                raise TypeError("protection must be WorkspaceProtection.")

            if protection.workspace != resolver.workspace:
                raise ValueError(
                    "Protection workspace must match resolver workspace."
                )

        self._resolver = resolver
        self._protection = protection

    def inspect(
        self,
        path: str | Path,
        *,
        allow_protected_read: bool = False,
    ) -> FileMetadata:
        """Return metadata for a validated workspace entry."""

        resolved = self._resolver.resolve(
            path,
            must_exist=True,
        )

        target = resolved.absolute

        if target.is_symlink():
            raise MetadataInspectionError(
                "Symbolic link metadata inspection is not permitted."
            )

        if self._protection is not None and not allow_protected_read:
            decision = self._protection.inspect(
                target,
                operation="read",
            )

            if not decision.allowed:
                raise MetadataInspectionError(decision.reason)

        try:
            metadata = target.stat(follow_symlinks=False)

            if stat.S_ISREG(metadata.st_mode):
                entry_type = "file"
                size = metadata.st_size
            elif stat.S_ISDIR(metadata.st_mode):
                entry_type = "directory"
                size = 0
            else:
                raise MetadataInspectionError(
                    "Unsupported filesystem entry type."
                )

            relative = target.relative_to(
                self._resolver.workspace
            ).as_posix()

            return FileMetadata(
                name=target.name,
                path=target,
                relative_path=relative,
                entry_type=entry_type,
                size_bytes=size,
                extension=(
                    target.suffix.lower()
                    if entry_type == "file" and target.suffix
                    else None
                ),
                created_at=self._timestamp(metadata.st_ctime),
                modified_at=self._timestamp(metadata.st_mtime),
                accessed_at=self._timestamp(metadata.st_atime),
                mode=stat.S_IMODE(metadata.st_mode),
                readable=os.access(target, os.R_OK),
                writable=os.access(target, os.W_OK),
                executable=os.access(target, os.X_OK),
                is_hidden=target.name.startswith("."),
                is_symlink=False,
            )

        except OSError as exc:
            raise MetadataInspectionError(
                f"Could not inspect metadata: {target}"
            ) from exc

    @staticmethod
    def _timestamp(value: float) -> datetime:
        """Convert filesystem timestamps to timezone-aware UTC."""

        return datetime.fromtimestamp(
            value,
            tz=UTC,
        )
