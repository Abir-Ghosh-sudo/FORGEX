"""Secure workspace file and directory operations."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver
from forgex.tools.filesystem.protection import WorkspaceProtection


class FileOperationError(Exception):
    """Base exception for filesystem operation failures."""


class DestinationExistsError(FileOperationError):
    """Raised when an operation would overwrite an existing destination."""


class InvalidOperationError(FileOperationError):
    """Raised when a filesystem operation is invalid."""


class ProtectedFileOperationError(FileOperationError):
    """Raised when an operation targets a protected path."""


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
        protection: WorkspaceProtection | None = None,
        max_copy_size: int = 100 * 1024 * 1024,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        if max_copy_size <= 0:
            raise ValueError("max_copy_size must be positive.")

        if protection is not None:
            if not isinstance(protection, WorkspaceProtection):
                raise TypeError("protection must be WorkspaceProtection.")

            if protection.workspace != resolver.workspace:
                raise ValueError("Protection workspace must match resolver workspace.")

        self._resolver = resolver
        self._protection = protection
        self._max_copy_size = max_copy_size

    def copy(
        self,
        source: str | Path,
        destination: str | Path,
        *,
        overwrite: bool = False,
        create_parents: bool = False,
    ) -> FileOperationResult:
        """Copy a regular file or directory."""

        src = self._resolver.resolve(source, must_exist=True)
        dst = self._resolver.resolve(destination)

        self._validate_source(src.absolute, operation="copy")
        self._validate_destination(
            src.absolute,
            dst.absolute,
            operation="write",
            overwrite=overwrite,
        )

        if not dst.absolute.parent.exists():
            if not create_parents:
                raise FileOperationError("Destination parent directory does not exist.")
            dst.absolute.parent.mkdir(parents=True, exist_ok=True)

        self._resolver.resolve(dst.absolute.parent, must_exist=True)
        self._check_protection(dst.absolute, "write")

        if src.is_file:
            size = src.absolute.stat().st_size

            if size > self._max_copy_size:
                raise InvalidOperationError(f"File exceeds the {self._max_copy_size}-byte limit.")

            self._copy_file(
                src.absolute,
                dst.absolute,
                overwrite=overwrite,
            )

            return FileOperationResult(
                operation="copy",
                source=src.absolute,
                destination=dst.absolute,
                is_directory=False,
                bytes_copied=size,
            )

        if src.is_directory:
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
        """Move a file or directory inside the workspace."""

        src = self._resolver.resolve(source, must_exist=True)
        dst = self._resolver.resolve(destination)

        self._validate_source(src.absolute, operation="move")
        self._validate_destination(
            src.absolute,
            dst.absolute,
            operation="move",
            overwrite=overwrite,
        )

        if not dst.absolute.parent.exists():
            if not create_parents:
                raise FileOperationError("Destination parent directory does not exist.")
            dst.absolute.parent.mkdir(parents=True, exist_ok=True)

        self._resolver.resolve(dst.absolute.parent, must_exist=True)
        self._check_protection(dst.absolute, "move")

        try:
            if overwrite and dst.absolute.exists():
                self._remove_existing(dst.absolute)

            # Revalidate immediately before mutation.
            self._resolver.resolve(src.absolute, must_exist=True)
            self._resolver.resolve(dst.absolute)

            self._check_protection(src.absolute, "move")
            self._check_protection(dst.absolute, "move")

            os.replace(src.absolute, dst.absolute)

        except FileOperationError:
            raise
        except OSError as exc:
            raise FileOperationError(f"Could not move {src.absolute} to {dst.absolute}.") from exc

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
        """Rename an entry within its existing parent directory."""

        if (
            not isinstance(new_name, str)
            or not new_name
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
    ) -> None:
        """Copy through a temporary file before atomic installation."""

        temporary: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".forgex-copy-",
                suffix=".tmp",
                dir=destination.parent,
                delete=False,
            ) as target:
                temporary = Path(target.name)

                with source.open("rb") as original:
                    shutil.copyfileobj(
                        original,
                        target,
                        length=1024 * 1024,
                    )

                target.flush()
                os.fsync(target.fileno())

            self._resolver.resolve(source, must_exist=True)
            self._resolver.resolve(destination)
            self._check_protection(source, "copy")
            self._check_protection(destination, "write")

            if destination.is_symlink():
                raise InvalidOperationError("Symlink destinations are not permitted.")

            if overwrite:
                os.replace(temporary, destination)
            else:
                # Atomic no-overwrite installation on the same filesystem.
                os.link(temporary, destination)
                temporary.unlink()

            temporary = None

        except FileExistsError as exc:
            raise DestinationExistsError(f"Destination already exists: {destination}") from exc
        except (FileOperationError, InvalidOperationError):
            raise
        except OSError as exc:
            raise FileOperationError(f"Could not copy file: {source}") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _copy_directory(
        self,
        source: Path,
        destination: Path,
        *,
        overwrite: bool,
    ) -> None:
        """Copy a directory without following symbolic links."""

        if destination == source or source in destination.parents:
            raise InvalidOperationError("Cannot copy a directory into itself or its descendants.")

        if destination.exists():
            if not overwrite:
                raise DestinationExistsError(f"Destination already exists: {destination}")
            self._remove_existing(destination)

        copied_paths: list[Path] = []

        def validate_tree(root: Path) -> None:
            for current, directories, files in os.walk(
                root,
                topdown=True,
                followlinks=False,
            ):
                current_path = Path(current)

                for name in list(directories):
                    item = current_path / name

                    if item.is_symlink():
                        raise InvalidOperationError(f"Symlink directory is not permitted: {item}")

                    directories.remove(name) if name == ".forgex-trash" else None

                for name in files:
                    item = current_path / name

                    if item.is_symlink():
                        raise InvalidOperationError(f"Symlink file is not permitted: {item}")

                    if item.stat().st_size > self._max_copy_size:
                        raise InvalidOperationError(f"File exceeds copy size limit: {item}")

        try:
            validate_tree(source)
            self._check_protection(source, "copy")

            shutil.copytree(
                source,
                destination,
                symlinks=False,
                ignore_dangling_symlinks=True,
            )

            for current, directories, files in os.walk(
                destination,
                followlinks=False,
            ):
                for name in directories + files:
                    item = Path(current) / name
                    copied_paths.append(item)

            for item in copied_paths:
                self._resolver.resolve(item, must_exist=True)
                self._check_protection(item, "write")

        except Exception:
            if destination.exists():
                self._remove_existing(destination)
            raise

    def _validate_source(
        self,
        source: Path,
        *,
        operation: str,
    ) -> None:
        if source == self._resolver.workspace:
            raise InvalidOperationError("The workspace root cannot be modified.")

        if source.is_symlink():
            raise InvalidOperationError("Symlink operations are not permitted.")

        self._check_protection(source, operation)

    def _validate_destination(
        self,
        source: Path,
        destination: Path,
        *,
        operation: str,
        overwrite: bool,
    ) -> None:
        if destination == self._resolver.workspace:
            raise InvalidOperationError("The workspace root cannot be a destination.")

        if source == destination:
            raise InvalidOperationError("Source and destination are identical.")

        if source.is_dir() and source in destination.parents:
            raise InvalidOperationError("Destination cannot be inside the source directory.")

        if destination.is_symlink():
            raise InvalidOperationError("Symlink destinations are not permitted.")

        if destination.exists() and not overwrite:
            raise DestinationExistsError(f"Destination already exists: {destination}")

        self._resolver.resolve(destination)
        self._check_protection(source, operation)
        self._check_protection(destination, operation)

    def _check_protection(
        self,
        path: Path,
        operation: str,
    ) -> None:
        if self._protection is None:
            return

        result = self._protection.inspect(
            path,
            operation=operation,
        )

        if not result.allowed:
            raise ProtectedFileOperationError(result.reason)

    @staticmethod
    def _remove_existing(path: Path) -> None:
        """Remove a destination without following symlinks."""

        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            raise InvalidOperationError(f"Unsupported destination object: {path}")
