
"""Secure workspace file writing utilities."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import WorkspacePathResolver
from forgex.tools.filesystem.protection import WorkspaceProtection


class FileWriteError(Exception):
    """Base exception for file writing failures."""


class FileWritePermissionError(FileWriteError):
    """Raised when a write operation is not permitted."""


@dataclass(frozen=True, slots=True)
class FileWriteResult:
    """Result of a file writing operation."""

    path: Path
    bytes_written: int
    created: bool
    overwritten: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "bytes_written": self.bytes_written,
            "created": self.created,
            "overwritten": self.overwritten,
        }


class FileWriter:
    """Write files safely inside a validated workspace."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        protection: WorkspaceProtection | None = None,
        max_write_size: int = 10 * 1024 * 1024,
        create_parents: bool = True,
    ) -> None:
        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        if max_write_size <= 0:
            raise ValueError("max_write_size must be positive.")

        if not isinstance(create_parents, bool):
            raise TypeError("create_parents must be a boolean.")

        if protection is not None:
            if not isinstance(protection, WorkspaceProtection):
                raise TypeError("protection must be WorkspaceProtection.")

            if protection.workspace != resolver.workspace:
                raise ValueError(
                    "Protection workspace must match resolver workspace."
                )

        self._resolver = resolver
        self._protection = protection
        self._max_write_size = max_write_size
        self._create_parents = create_parents

    def write_text(
        self,
        path: str | Path,
        content: str,
        *,
        encoding: str = "utf-8",
        overwrite: bool = False,
    ) -> FileWriteResult:
        """Write encoded text atomically."""

        if not isinstance(content, str):
            raise TypeError("content must be a string.")

        return self.write_bytes(
            path,
            content.encode(encoding),
            overwrite=overwrite,
        )

    def write_bytes(
        self,
        path: str | Path,
        content: bytes,
        *,
        overwrite: bool = False,
    ) -> FileWriteResult:
        """Write bytes using a temporary file and atomic installation."""

        if not isinstance(content, bytes):
            raise TypeError("content must be bytes.")

        if not isinstance(overwrite, bool):
            raise TypeError("overwrite must be a boolean.")

        if len(content) > self._max_write_size:
            raise FileWriteError(
                f"Content exceeds the {self._max_write_size}-byte limit."
            )

        # Resolve the caller-provided path exactly once initially.
        resolved = self._resolver.resolve(path)
        destination = resolved.absolute

        self._check_protection(destination)

        if destination == self._resolver.workspace:
            raise FileWriteError("Cannot write to the workspace root.")

        parent = destination.parent

        if not parent.exists():
            if not self._create_parents:
                raise FileWriteError("Parent directory does not exist.")

            parent.mkdir(parents=True, exist_ok=True)

        temporary_path: Path | None = None

        try:
            # Revalidate using the original path, never the absolute path.
            resolved = self._resolver.resolve(path)
            destination = resolved.absolute
            parent = destination.parent

            self._check_protection(destination)

            if destination == self._resolver.workspace:
                raise FileWriteError("Cannot write to the workspace root.")

            if not parent.is_dir():
                raise FileWriteError("Parent directory does not exist.")

            if destination.is_symlink():
                raise FileWriteError(
                    "Writing through symlinks is not permitted."
                )

            existed = destination.exists()

            if existed and not destination.is_file():
                raise FileWriteError("Destination is not a regular file.")

            if existed and not overwrite:
                raise FileWriteError(
                    f"Destination already exists: {destination}"
                )

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".forgex-write-",
                suffix=".tmp",
                dir=parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())

            # Final containment and protection check before installation.
            latest = self._resolver.resolve(path)
            destination = latest.absolute
            self._check_protection(destination)

            if destination.is_symlink():
                raise FileWriteError(
                    "Destination became a symlink during writing."
                )

            if destination.parent != parent:
                raise FileWriteError(
                    "Destination parent changed during writing."
                )

            if overwrite:
                os.replace(temporary_path, destination)
            else:
                # Atomic no-overwrite installation.
                os.link(temporary_path, destination)
                temporary_path.unlink()

            temporary_path = None

            return FileWriteResult(
                path=destination,
                bytes_written=len(content),
                created=not existed,
                overwritten=existed,
            )

        except FileWriteError:
            raise
        except FileExistsError as exc:
            raise FileWriteError(
                f"Destination already exists: {destination}"
            ) from exc
        except OSError as exc:
            raise FileWriteError(
                f"Could not write file: {destination}"
            ) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _check_protection(self, path: Path) -> None:
        """Reject writes targeting protected paths."""

        if self._protection is None:
            return

        result = self._protection.inspect(
            path,
            operation="write",
        )

        if not result.allowed:
            raise FileWritePermissionError(result.reason)
