
"""Safe file and directory copy, move and rename operations."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver

logger = logging.getLogger(__name__)


class FileOperationError(Exception):
    """Base exception for filesystem operation failures."""


class DestinationExistsError(FileOperationError):
    """Raised when an operation would overwrite an existing destination."""


class InvalidOperationError(FileOperationError):
    """Raised when a filesystem operation is invalid."""


@dataclass(frozen=True, slots=True)
class FileOperationResult:
    """Result of a copy, move or rename operation."""

    operation: str
    source: Path
    destination: Path
    is_directory: bool
    bytes_copied: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "source": str(self.source),
            "destination": str(self.destination),
            "is_directory": self.is_directory,
            "bytes_copied": self.bytes_copied,
        }


class FileOperations:
    """Perform workspace-confined filesystem operations."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        max_copy_size: int = 100 * 1024 * 1024,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        if max_copy_size <= 0:
            raise ValueError("max_copy_size must be positive.")

        self._resolver = resolver
        self._max_copy_size = max_copy_size

    def copy(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        overwrite: bool = False,
        create_parents: bool = False,
    ) -> FileOperationResult:
        """Copy a file or directory within the workspace."""

        src = self._resolver.resolve(source, must_exist=True)
        dst = self._resolver.resolve(destination)

        self._validate_source(src.absolute)
        self._validate_destination(
            src.absolute,
            dst.absolute,
            overwrite=overwrite,
        )

        if src.is_file:
            size = src.absolute.stat().st_size

            if size > self._max_copy_size:
                raise InvalidOperationError(
                    f"File exceeds the {self._max_copy_size}-byte copy limit."
                )

            if not dst.absolute.parent.exists():
                if not create_parents:
                    raise FileOperationError(
                        "Destination parent directory does not exist."
                    )
                dst.absolute.parent.mkdir(parents=True, exist_ok=True)

            return self._copy_file(
                src.absolute,
                dst.absolute,
                overwrite=overwrite,
                size=size,
            )

        if src.is_directory:
            if not dst.absolute.parent.exists():
                if not create_parents:
                    raise FileOperationError(
                        "Destination parent directory does not exist."
                    )
                dst.absolute.parent.mkdir(parents=True, exist_ok=True)

            self._copy_directory(
                src.absolute,
                dst.absolute,
                overwrite=overwrite,
            )

            return FileOperationResult(
                operation="copy",
                source=src.absolute,
                destination=dst.absolute,
                is_directory=True,
            )

        raise InvalidOperationError("Unsupported source filesystem object.")

    def move(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        overwrite: bool = False,
        create_parents: bool = False,
    ) -> FileOperationResult:
        """Move a file or directory within the workspace."""

        src = self._resolver.resolve(source, must_exist=True)
        dst = self._resolver.resolve(destination)

        self._validate_source(src.absolute)
        self._validate_destination(
            src.absolute,
            dst.absolute,
            overwrite=overwrite,
        )

        if not dst.absolute.parent.exists():
            if not create_parents:
                raise FileOperationError(
                    "Destination parent directory does not exist."
                )
            dst.absolute.parent.mkdir(parents=True, exist_ok=True)

        try:
            if overwrite and dst.absolute.exists():
                self._remove_existing(dst.absolute)

            os.replace(src.absolute, dst.absolute)

        except OSError as exc:
            logger.exception("Move failed: %s -> %s", src.absolute, dst.absolute)
            raise FileOperationError(
                f"Could not move {src.absolute} to {dst.absolute}."
            ) from exc

        return FileOperationResult(
            operation="move",
            source=src.absolute,
            destination=dst.absolute,
            is_directory=src.is_directory,
        )

    def rename(
        self,
        source: str | Path,
        new_name: str,
        *,
        overwrite: bool = False,
    ) -> FileOperationResult:
        """Rename an entry without changing its parent directory."""

        if (
            not new_name
            or new_name in {".", ".."}
            or Path(new_name).name != new_name
            or "/" in new_name
            or "\\" in new_name
            or "\x00" in new_name
        ):
            raise InvalidOperationError("Invalid destination name.")

        src = self._resolver.resolve(source, must_exist=True)
        destination = src.absolute.with_name(new_name)

        return self.move(
            src.absolute,
            destination,
            overwrite=overwrite,
        )

    def _copy_file(
        self,
        source: Path,
        destination: Path,
        *,
        overwrite: bool,
        size: int,
    ) -> FileOperationResult:
        """Copy a file through a temporary file and atomic replacement."""

        temporary = destination.parent / f".forgex-copy-{uuid.uuid4().hex}.tmp"

        try:
            with source.open("rb") as source_file:
                with temporary.open("xb") as target_file:
                    shutil.copyfileobj(
                        source_file,
                        target_file,
                        length=1024 * 1024,
                    )
                    target_file.flush()
                    os.fsync(target_file.fileno())

            self._resolver.resolve(destination)

            if not overwrite and destination.exists():
                raise DestinationExistsError(
                    f"Destination appeared during copy: {destination}"
                )

            os.replace(temporary, destination)

        except Exception:
            temporary.unlink(missing_ok=True)
            raise

        return FileOperationResult(
            operation="copy",
            source=source,
            destination=destination,
            is_directory=False,
            bytes_copied=size,
        )

    def _copy_directory(
        self,
        source: Path,
        destination: Path,
        *,
        overwrite: bool,
    ) -> None:
        """Copy a directory without following symbolic links."""

        if destination == source or source in destination.parents:
            raise InvalidOperationError(
                "Cannot copy a directory into itself or its descendants."
            )

        if destination.exists():
            if not overwrite:
                raise DestinationExistsError(
                    f"Destination already exists: {destination}"
                )
            self._remove_existing(destination)

        try:
            shutil.copytree(
                source,
                destination,
                symlinks=True,
                ignore_dangling_symlinks=True,
            )

            for copied in destination.rglob("*"):
                if copied.is_symlink():
                    raise InvalidOperationError(
                        f"Symlinks are not allowed in copied directories: {copied}"
                    )

                if copied.is_file():
                    if copied.stat().st_size > self._max_copy_size:
                        raise InvalidOperationError(
                            f"Copied file exceeds size limit: {copied}"
                        )

        except Exception:
            if destination.exists():
                self._remove_existing(destination)
            raise

    def _validate_source(self, source: Path) -> None:
        """Reject unsupported source paths and protected workspace root."""

        if source == self._resolver.workspace:
            raise InvalidOperationError(
                "The workspace root cannot be copied or moved."
            )

        if source.is_symlink():
            raise InvalidOperationError("Symlink operations are not permitted.")

    def _validate_destination(
        self,
        source: Path,
        destination: Path,
        *,
        overwrite: bool,
    ) -> None:
        """Validate destination containment and overwrite behavior."""

        if destination == self._resolver.workspace:
            raise InvalidOperationError(
                "The workspace root cannot be a destination."
            )

        if source == destination:
            raise InvalidOperationError(
                "Source and destination are identical."
            )

        if source.is_dir() and source in destination.parents:
            raise InvalidOperationError(
                "Destination cannot be inside the source directory."
            )

        if destination.exists() and not overwrite:
            raise DestinationExistsError(
                f"Destination already exists: {destination}"
            )

        if destination.is_symlink():
            raise InvalidOperationError(
                "Symlink destinations are not permitted."
            )

        # Re-resolve immediately before filesystem changes.
        self._resolver.resolve(destination)

    @staticmethod
    def _remove_existing(path: Path) -> None:
        """Remove an existing destination without following symlinks."""

        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            raise InvalidOperationError(
                f"Unsupported destination object: {path}"
            )
