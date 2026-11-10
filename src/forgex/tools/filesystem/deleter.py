
"""Recoverable file deletion utilities for FORGEX."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver

logger = logging.getLogger(__name__)

TRASH_DIRECTORY = ".forgex-trash"


class FileDeleteError(Exception):
    """Base exception for deletion failures."""


class PermanentDeleteDeniedError(FileDeleteError):
    """Raised when permanent deletion is not explicitly authorized."""


@dataclass(frozen=True, slots=True)
class FileDeleteResult:
    """Result of a deletion operation."""

    original_path: Path
    stored_path: Path | None
    permanent: bool
    deleted_at: datetime

    @property
    def recoverable(self) -> bool:
        return self.stored_path is not None and not self.permanent

    def to_dict(self) -> dict[str, object]:
        return {
            "original_path": str(self.original_path),
            "stored_path": (
                str(self.stored_path) if self.stored_path else None
            ),
            "permanent": self.permanent,
            "recoverable": self.recoverable,
            "deleted_at": self.deleted_at.isoformat(),
        }


class FileDeleter:
    """Delete files and directories with recoverable trash support."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        trash_directory: str = TRASH_DIRECTORY,
        allow_permanent_delete: bool = False,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        if not trash_directory or Path(trash_directory).is_absolute():
            raise ValueError("trash_directory must be a relative path.")

        trash_path = Path(trash_directory)

        if ".." in trash_path.parts or len(trash_path.parts) != 1:
            raise ValueError(
                "trash_directory must be a single safe directory name."
            )

        self._resolver = resolver
        self._trash_name = trash_path.name
        self._allow_permanent_delete = allow_permanent_delete

    def delete(
        self,
        path: str | Path,
        *,
        permanent: bool = False,
        confirm_permanent: bool = False,
    ) -> FileDeleteResult:
        """Move a path to trash or permanently delete it."""

        target = self._resolver.resolve(path, must_exist=True)
        original = target.absolute

        if original == self._resolver.workspace:
            raise FileDeleteError(
                "Deleting the workspace root is forbidden."
            )

        if self._trash_name in target.relative.parts:
            raise FileDeleteError(
                "Direct deletion of the FORGEX trash directory is forbidden."
            )

        if permanent:
            if not self._allow_permanent_delete:
                raise PermanentDeleteDeniedError(
                    "Permanent deletion is disabled by configuration."
                )

            if not confirm_permanent:
                raise PermanentDeleteDeniedError(
                    "Permanent deletion requires explicit confirmation."
                )

            self._remove_path(original)

            return FileDeleteResult(
                original_path=original,
                stored_path=None,
                permanent=True,
                deleted_at=datetime.now(UTC),
            )

        trash_root = self._resolver.workspace / self._trash_name
        self._ensure_trash_directory(trash_root)

        deletion_id = uuid.uuid4().hex
        destination = trash_root / deletion_id

        # Revalidate the target and trash boundary before moving.
        current = self._resolver.resolve(original, must_exist=True)
        if current.absolute != original:
            raise FileDeleteError(
                "Target path changed during deletion."
            )

        try:
            os.replace(original, destination)
        except OSError as exc:
            logger.exception("Could not move path to trash: %s", original)
            raise FileDeleteError(
                f"Could not move path to trash: {original}"
            ) from exc

        return FileDeleteResult(
            original_path=original,
            stored_path=destination,
            permanent=False,
            deleted_at=datetime.now(UTC),
        )

    def restore(self, deletion: FileDeleteResult) -> Path:
        """Restore a previously trashed file or directory."""

        if not isinstance(deletion, FileDeleteResult):
            raise TypeError("deletion must be a FileDeleteResult.")

        if not deletion.recoverable or deletion.stored_path is None:
            raise FileDeleteError("This deletion cannot be recovered.")

        stored = deletion.stored_path
        original = deletion.original_path

        expected_trash = self._resolver.workspace / self._trash_name

        try:
            stored_resolved = stored.resolve(strict=True)
            stored_resolved.relative_to(expected_trash.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise FileDeleteError(
                "Stored path is outside the FORGEX trash directory."
            ) from exc

        try:
            original.relative_to(self._resolver.workspace)
        except ValueError as exc:
            raise FileDeleteError(
                "Original path is outside the workspace."
            ) from exc

        if not stored.exists():
            raise FileDeleteError(
                f"Trashed item no longer exists: {stored}"
            )

        if original.exists():
            raise FileDeleteError(
                f"Cannot restore because destination exists: {original}"
            )

        parent = original.parent

        try:
            parent_resolved = parent.resolve(strict=True)
            parent_resolved.relative_to(self._resolver.workspace)
        except (OSError, ValueError) as exc:
            raise FileDeleteError(
                "Restore parent is missing or outside the workspace."
            ) from exc

        if not parent_resolved.is_dir():
            raise FileDeleteError("Restore parent is not a directory.")

        try:
            os.replace(stored_resolved, original)
        except OSError as exc:
            raise FileDeleteError(
                f"Could not restore item: {original}"
            ) from exc

        return original

    def _ensure_trash_directory(self, trash_root: Path) -> None:
        """Create or validate the workspace trash directory."""

        if trash_root.is_symlink():
            raise FileDeleteError(
                "Trash directory cannot be a symlink."
            )

        if not trash_root.exists():
            try:
                trash_root.mkdir(mode=0o700)
            except OSError as exc:
                raise FileDeleteError(
                    "Could not create FORGEX trash directory."
                ) from exc

        if not trash_root.is_dir() or trash_root.is_symlink():
            raise FileDeleteError(
                "FORGEX trash path is not a safe directory."
            )

        try:
            trash_root.resolve(strict=True).relative_to(
                self._resolver.workspace
            )
        except (OSError, ValueError) as exc:
            raise FileDeleteError(
                "Trash directory escapes the workspace."
            ) from exc

    @staticmethod
    def _remove_path(path: Path) -> None:
        """Remove a file, symlink or directory without following symlinks."""

        try:
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)
            else:
                raise FileDeleteError(
                    f"Unsupported filesystem object: {path}"
                )
        except FileDeleteError:
            raise
        except OSError as exc:
            raise FileDeleteError(
                f"Could not permanently delete: {path}"
            ) from exc
