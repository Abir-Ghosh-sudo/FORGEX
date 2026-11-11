"""Secure file reading utilities for FORGEX."""

from __future__ import annotations

import codecs
import logging
from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.paths import (
    ResolvedPath,
    WorkspacePathResolver,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILE_SIZE = 5 * 1024 * 1024
DEFAULT_ENCODING = "utf-8"


class FileReadError(Exception):
    """Base exception for file reading failures."""


class FileTooLargeError(FileReadError):
    """Raised when a file exceeds the configured size limit."""


class BinaryFileError(FileReadError):
    """Raised when a binary file is encountered."""


class UnsupportedEncodingError(FileReadError):
    """Raised when the requested encoding is invalid."""


@dataclass(frozen=True, slots=True)
class FileReadResult:
    """Result of a successful file read."""

    path: Path
    content: str
    encoding: str
    size_bytes: int
    line_count: int
    truncated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "content": self.content,
            "encoding": self.encoding,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "truncated": self.truncated,
        }


class FileReader:
    """Read text files within a validated workspace."""

    def __init__(
        self,
        resolver: WorkspacePathResolver,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        default_encoding: str = DEFAULT_ENCODING,
        detect_encoding: bool = True,
        reject_binary: bool = True,
    ) -> None:
        if max_file_size <= 0:
            raise ValueError("max_file_size must be positive.")

        if not isinstance(resolver, WorkspacePathResolver):
            raise TypeError("resolver must be a WorkspacePathResolver.")

        try:
            codecs.lookup(default_encoding)
        except LookupError as exc:
            raise UnsupportedEncodingError(f"Unknown encoding: {default_encoding}") from exc

        self._resolver = resolver
        self._max_file_size = max_file_size
        self._default_encoding = default_encoding
        self._detect_encoding = detect_encoding
        self._reject_binary = reject_binary

    def read(
        self,
        path: str | Path,
        *,
        encoding: str | None = None,
        max_bytes: int | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        allow_truncation: bool = False,
    ) -> FileReadResult:
        """Read a text file with optional line-range selection.

        Line numbers are one-based and inclusive.
        """

        resolved = self._resolver.resolve(
            path,
            must_exist=True,
            expected_type="file",
        )

        limit = self._max_file_size if max_bytes is None else max_bytes

        if limit <= 0:
            raise ValueError("max_bytes must be positive.")

        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be at least 1.")

        if end_line is not None and end_line < 1:
            raise ValueError("end_line must be at least 1.")

        if start_line is not None and end_line is not None and end_line < start_line:
            raise ValueError("end_line cannot precede start_line.")

        try:
            content_bytes, truncated = self._read_bytes(
                resolved,
                limit=limit,
                allow_truncation=allow_truncation,
            )

            if self._reject_binary and self._looks_binary(content_bytes):
                raise BinaryFileError(f"Binary files cannot be read as text: {resolved.absolute}")

            selected_encoding = self._select_encoding(
                content_bytes,
                requested=encoding,
            )

            try:
                content = content_bytes.decode(
                    selected_encoding,
                    errors="replace" if allow_truncation else "strict",
                )
            except UnicodeDecodeError as exc:
                raise UnsupportedEncodingError(
                    f"Unable to decode {resolved.absolute} using {selected_encoding}."
                ) from exc

            if start_line is not None or end_line is not None:
                lines = content.splitlines(keepends=True)
                first = (start_line or 1) - 1
                last = end_line if end_line is not None else len(lines)
                content = "".join(lines[first:last])

            return FileReadResult(
                path=resolved.absolute,
                content=content,
                encoding=selected_encoding,
                size_bytes=len(content_bytes),
                line_count=len(content.splitlines()),
                truncated=truncated,
            )

        except FileReadError:
            raise
        except OSError as exc:
            logger.exception("Failed to read file: %s", resolved.absolute)
            raise FileReadError(f"Could not read file: {resolved.absolute}") from exc

    def _read_bytes(
        self,
        resolved: ResolvedPath,
        *,
        limit: int,
        allow_truncation: bool,
    ) -> tuple[bytes, bool]:
        """Read at most limit + 1 bytes to detect oversized files."""

        with resolved.absolute.open("rb") as file:
            data = file.read(limit + 1)

        if len(data) > limit:
            if not allow_truncation:
                raise FileTooLargeError(
                    f"File exceeds the {limit}-byte read limit: {resolved.absolute}"
                )

            return data[:limit], True

        return data, False

    def _select_encoding(
        self,
        data: bytes,
        *,
        requested: str | None,
    ) -> str:
        """Select encoding using an explicit value or BOM detection."""

        if requested is not None:
            try:
                return codecs.lookup(requested).name
            except LookupError as exc:
                raise UnsupportedEncodingError(f"Unknown encoding: {requested}") from exc

        if self._detect_encoding:
            if data.startswith(codecs.BOM_UTF8):
                return "utf-8-sig"
            if data.startswith(codecs.BOM_UTF16_LE):
                return "utf-16"
            if data.startswith(codecs.BOM_UTF16_BE):
                return "utf-16"
            if data.startswith(codecs.BOM_UTF32_LE):
                return "utf-32"
            if data.startswith(codecs.BOM_UTF32_BE):
                return "utf-32"

        return self._default_encoding

    @staticmethod
    def _looks_binary(data: bytes) -> bool:
        """Detect likely binary content without rejecting normal UTF text."""

        if not data:
            return False

        if b"\x00" in data:
            return True

        sample = data[:8192]
        control_bytes = sum(byte < 32 and byte not in (7, 8, 9, 10, 12, 13, 27) for byte in sample)

        return control_bytes / len(sample) > 0.10
