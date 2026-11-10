
"""Secure and atomic file writing utilities for FORGEX."""

from __future__ import annotations

import codecs
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import (
    WorkspacePathResolver,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_WRITE_SIZE = 10 * 1024 * 1024


class FileWriteError(Exception):
    """Base exception for file writing failures."""


class FileAlreadyExistsError(FileWriteError):
    """Raised when overwrite is not permitted."""


class FileWriteSizeError(FileWriteError):
    """Raised when content exceeds the configured size limit."""


@dataclass(frozen=True, slots=True)
class FileWriteResult:
    """Result of a successful file write."""

    path: Path
    bytes_written: int
    created: bool
    atomic: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "bytes_written": self.bytes_written,
            "created": self.created,
            "atomic": self.atomic,
        }


class FileWriter:
    """Write files inside a validated workspace.

    Writes use a temporary file in the destination directory followed by
    an atomic replacement. Existing files are protected unless overwrite
    is explicitly enabled.
    """

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        max_write_size: int = DEFAULT_MAX_WRITE_SIZE,
        default_encoding: str = "utf-8",
        file_mode: int = 0o600,
    ) -> None:
        if max_write_size <= 0:
            raise ValueError("max_write_size must be positive.")

        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        try:
            codecs.lookup(default_encoding)
        except LookupError as exc:
            raise ValueError(
                f"Unknown encoding: {default_encoding}"
            ) from exc

        if file_mode < 0 or file_mode > 0o777:
            raise ValueError("file_mode must be between 0 and 0o777.")

        self._resolver = resolver
        self._max_write_size = max_write_size
        self._default_encoding = default_encoding
        self._file_mode = file_mode

    def write(
        self,
        path: str | Path,
        content: str | bytes,
        *,
        encoding: str | None = None,
        overwrite: bool = False,
        create_parents: bool = False,
    ) -> FileWriteResult:
        """Atomically write content to a workspace file."""

        if not isinstance(content, (str, bytes)):
            raise TypeError("content must be str or bytes.")

        if isinstance(content, str):
            selected_encoding = encoding or self._default_encoding
            try:
                data = content.encode(selected_encoding)
            except (LookupError, UnicodeEncodeError) as exc:
                raise FileWriteError(
                    f"Could not encode content using {selected_encoding}."
                ) from exc
        else:
            if encoding is not None:
                raise ValueError(
                    "encoding must not be specified when content is bytes."
                )
            data = content

        if len(data) > self._max_write_size:
            raise FileWriteSizeError(
                f"Content exceeds the {self._max_write_size}-byte limit."
            )

        resolved = self._resolver.resolve(path)
        destination = resolved.absolute
        parent = destination.parent

        if not parent.exists():
            if not create_parents:
                raise FileWriteError(
                    f"Parent directory does not exist: {parent}"
                )

            self._create_parent_directories(parent)

        # Revalidate after directory creation.
        resolved = self._resolver.resolve(path)
        destination = resolved.absolute
        parent = destination.parent

        if destination.exists() and destination.is_dir():
            raise FileWriteError(
                f"Destination is a directory: {destination}"
            )

        created = not destination.exists()

        if not overwrite and not created:
            raise FileAlreadyExistsError(
                f"File already exists: {destination}"
            )

        temporary_path: Path | None = None

        try:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=".forgex-",
                suffix=".tmp",
                dir=parent,
            )
            temporary_path = Path(temporary_name)

            try:
                if os.name != "nt":
                    os.fchmod(file_descriptor, self._file_mode)

                with os.fdopen(file_descriptor, "wb") as file:
                    file.write(data)
                    file.flush()
                    os.fsync(file.fileno())

            except Exception:
                # fdopen owns the descriptor once successfully constructed.
                try:
                    os.close(file_descriptor)
                except OSError:
                    pass
                raise

            # Revalidate immediately before replacement.
            self._resolver.resolve(path)

            if not overwrite and destination.exists():
                raise FileAlreadyExistsError(
                    f"File appeared during write: {destination}"
                )

            os.replace(temporary_path, destination)
            temporary_path = None

            self._fsync_directory(parent)

            return FileWriteResult(
                path=destination,
                bytes_written=len(data),
                created=created,
                atomic=True,
            )

        except FileWriteError:
            raise
        except OSError as exc:
            logger.exception("Failed to write file: %s", destination)
            raise FileWriteError(
                f"Could not write file: {destination}"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning(
                        "Could not remove temporary file: %s",
                        temporary_path,
                    )

    def _create_parent_directories(self, parent: Path) -> None:
        """Create missing directories one level at a time."""

        try:
            relative = parent.relative_to(self._resolver.workspace)
        except ValueError as exc:
            raise FileWriteError(
                "Parent directory escapes the workspace."
            ) from exc

        current = self._resolver.workspace

        for component in relative.parts:
            current = current / component

            if current.exists():
                if current.is_symlink() or not current.is_dir():
                    raise FileWriteError(
                        f"Unsafe parent directory: {current}"
                    )
                continue

            current.mkdir(mode=0o700)

            if current.is_symlink():
                raise FileWriteError(
                    f"Unexpected symlink in parent directory: {current}"
                )

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        """Best-effort directory sync for rename durability on POSIX."""

        if os.name == "nt":
            return

        descriptor: int | None = None

        try:
            descriptor = os.open(directory, os.O_RDONLY)
            os.fsync(descriptor)
        except OSError:
            logger.debug(
                "Directory fsync unavailable: %s",
                directory,
                exc_info=True,
            )
        finally:
            if descriptor is not None:
                os.close(descriptor)
