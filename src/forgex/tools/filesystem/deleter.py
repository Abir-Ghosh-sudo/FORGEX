"""Secure and recoverable workspace file deletion."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver
from forgex.tools.filesystem.protection import WorkspaceProtection

logger = logging.getLogger(__name__)


class FileDeletionError(Exception):
    """Base exception for file deletion failures."""


class PermanentDeletionDenied(FileDeletionError):
    """Raised when permanent deletion is not explicitly permitted."""


class ProtectedDeletionError(FileDeletionError):
    """Raised when attempting to delete a protected path."""


@dataclass(frozen=True, slots=True)
class FileDeletionResult:
    """Information required to restore a deleted entry."""

    original_path: Path
    trash_path: Path
    is_directory: bool
    permanent: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "original_path": str(self.original_path),
            "trash_path": str(self.trash_path),
            "is_directory": self.is_directory,
            "permanent": self.permanent,
        }


class FileDeleter:
    """Delete workspace entries with recoverable trash support."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        protection: WorkspaceProtection | None = None,
        allow_permanent_delete: bool = False,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be WorkspacePathResolver.")

        if protection is not None:
            if not isinstance(protection, WorkspaceProtection):
                raise TypeError("protection must be WorkspaceProtection.")

            if protection.workspace != resolver.workspace:
                raise ValueError("Protection workspace must match resolver workspace.")

        self._resolver = resolver
        self._protection = protection
        self._allow_permanent_delete = allow_permanent_delete
        self._trash_directory = resolver.workspace / ".forgex-trash"

    def delete(
        self,
        path: str | Path,
        *,
        permanent: bool = False,
        confirm: bool = False,
    ) -> FileDeletionResult:
        """Delete an entry, using recoverable trash by default."""

        resolved = self._resolver.resolve(path, must_exist=True)
        target = resolved.absolute

        self._validate_target(target)

        if permanent:
            if not self._allow_permanent_delete:
                raise PermanentDeletionDenied("Permanent deletion is disabled by configuration.")

            if not confirm:
                raise PermanentDeletionDenied("Permanent deletion requires explicit confirmation.")

            self._remove_target(target)

            return FileDeletionResult(
                original_path=target,
                trash_path=target,
                is_directory=resolved.is_directory,
                permanent=True,
            )

        self._ensure_trash_directory()

        trash_target = self._trash_directory / uuid.uuid4().hex

        # Validate again immediately before moving.
        self._resolver.resolve(target, must_exist=True)
        self._validate_target(target)

        try:
            os.replace(target, trash_target)
        except OSError as exc:
            raise FileDeletionError(f"Could not move entry to trash: {target}") from exc

        return FileDeletionResult(
            original_path=target,
            trash_path=trash_target,
            is_directory=resolved.is_directory,
        )

    def restore(self, result: FileDeletionResult) -> Path:
        """Restore an entry from trash to its original location."""

        if not isinstance(result, FileDeletionResult):
            raise TypeError("result must be FileDeletionResult.")

        if result.permanent:
            raise FileDeletionError("Permanently deleted entries cannot be restored.")

        if result.trash_path.parent != self._trash_directory:
            raise FileDeletionError("Invalid trash location.")

        if not result.trash_path.exists():
            raise FileDeletionError("Trash entry does not exist.")

        original = self._resolver.resolve(result.original_path)
        destination = original.absolute

        self._validate_target(destination)

        if destination.exists() or destination.is_symlink():
            raise FileDeletionError(f"Cannot restore: destination already exists: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)

        self._resolver.resolve(destination)

        try:
            os.replace(result.trash_path, destination)
        except OSError as exc:
            raise FileDeletionError(f"Could not restore entry: {destination}") from exc

        return destination

    def list_trash(self) -> tuple[Path, ...]:
        """List recoverable entries currently stored in trash."""

        self._ensure_trash_directory()

        try:
            return tuple(
                sorted(
                    self._trash_directory.iterdir(),
                    key=lambda item: item.name,
                )
            )
        except OSError as exc:
            raise FileDeletionError("Could not inspect trash directory.") from exc

    def _validate_target(self, target: Path) -> None:
        """Validate workspace boundaries and protected paths."""

        if target == self._resolver.workspace:
            raise FileDeletionError("The workspace root cannot be deleted.")

        if target == self._trash_directory:
            raise FileDeletionError("The trash directory cannot be deleted through this API.")

        if self._trash_directory in target.parents:
            raise FileDeletionError("Direct deletion of trash entries is not permitted.")

        if target.is_symlink():
            raise FileDeletionError("Symlink deletion is not permitted.")

        if self._protection is not None:
            result = self._protection.inspect(
                target,
                operation="delete",
            )

            if not result.allowed:
                raise ProtectedDeletionError(result.reason)

    def _ensure_trash_directory(self) -> None:
        """Create and validate the workspace trash directory."""

        if self._trash_directory.is_symlink():
            raise FileDeletionError("Trash directory cannot be a symlink.")

        self._trash_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self._trash_directory.is_dir():
            raise FileDeletionError("Trash location is not a directory.")

        self._resolver.resolve(
            self._trash_directory,
            must_exist=True,
            expected_type="directory",
        )

    @staticmethod
    def _remove_target(target: Path) -> None:
        """Permanently remove a file or directory."""

        try:
            if target.is_symlink() or target.is_file():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                raise FileDeletionError(f"Unsupported filesystem object: {target}")
        except OSError as exc:
            logger.exception("Permanent deletion failed: %s", target)
            raise FileDeletionError(f"Could not permanently delete: {target}") from exc
