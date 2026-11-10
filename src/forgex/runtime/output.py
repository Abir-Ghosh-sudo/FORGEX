
"""Bounded output buffering for FORGEX subprocess execution."""

from __future__ import annotations

import codecs
import threading
from collections import deque
from dataclasses import dataclass
from enum import StrEnum


class OutputStream(StrEnum):
    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass(frozen=True, slots=True)
class OutputSnapshot:
    """Immutable snapshot of captured process output."""

    stdout: str
    stderr: str
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    total_bytes_received: int

    @property
    def truncated(self) -> bool:
        return self.stdout_truncated or self.stderr_truncated


class _StreamBuffer:
    """Thread-safe bounded byte buffer."""

    def __init__(self, max_bytes: int) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive.")

        self.max_bytes = max_bytes
        self._chunks: deque[bytes] = deque()
        self._size = 0
        self._truncated = False
        self._lock = threading.Lock()

    def append(self, data: bytes) -> None:
        if not data:
            return

        if not isinstance(data, bytes):
            raise TypeError("Output data must be bytes.")

        with self._lock:
            if len(data) >= self.max_bytes:
                self._chunks.clear()
                self._chunks.append(data[-self.max_bytes:])
                self._size = self.max_bytes
                self._truncated = True
                return

            self._chunks.append(data)
            self._size += len(data)

            while self._size > self.max_bytes and self._chunks:
                overflow = self._size - self.max_bytes
                oldest = self._chunks[0]

                if len(oldest) <= overflow:
                    self._chunks.popleft()
                    self._size -= len(oldest)
                else:
                    self._chunks[0] = oldest[overflow:]
                    self._size -= overflow

                self._truncated = True

    def snapshot(self) -> tuple[bytes, bool]:
        with self._lock:
            return b"".join(self._chunks), self._truncated

    @property
    def size(self) -> int:
        with self._lock:
            return self._size


class ProcessOutputBuffer:
    """Capture bounded stdout and stderr independently.

    The buffer retains the most recent output, which is generally more
    useful for debugging than retaining only the beginning of a process log.
    """

    def __init__(
        self,
        max_bytes_per_stream: int = 1_048_576,
        encoding: str = "utf-8",
    ) -> None:
        if max_bytes_per_stream < 1:
            raise ValueError("max_bytes_per_stream must be positive.")

        try:
            codecs.lookup(encoding)
        except LookupError as exc:
            raise ValueError(f"Unknown encoding: {encoding}") from exc

        self.encoding = encoding
        self._stdout = _StreamBuffer(max_bytes_per_stream)
        self._stderr = _StreamBuffer(max_bytes_per_stream)
        self._total_bytes = 0
        self._total_lock = threading.Lock()

    def write(
        self,
        stream: OutputStream | str,
        data: bytes,
    ) -> None:
        """Append bytes to the selected output stream."""

        try:
            stream_type = OutputStream(stream)
        except ValueError as exc:
            raise ValueError(f"Unsupported output stream: {stream}") from exc

        if not isinstance(data, bytes):
            raise TypeError("Output data must be bytes.")

        if stream_type == OutputStream.STDOUT:
            self._stdout.append(data)
        else:
            self._stderr.append(data)

        with self._total_lock:
            self._total_bytes += len(data)

    def snapshot(self) -> OutputSnapshot:
        """Return a consistent-enough snapshot of both streams."""

        stdout, stdout_truncated = self._stdout.snapshot()
        stderr, stderr_truncated = self._stderr.snapshot()

        with self._total_lock:
            total = self._total_bytes

        return OutputSnapshot(
            stdout=stdout.decode(self.encoding, errors="replace"),
            stderr=stderr.decode(self.encoding, errors="replace"),
            stdout_bytes=len(stdout),
            stderr_bytes=len(stderr),
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
            total_bytes_received=total,
        )

    def clear(self) -> None:
        """Discard captured output and reset counters."""

        with self._stdout._lock:
            self._stdout._chunks.clear()
            self._stdout._size = 0
            self._stdout._truncated = False

        with self._stderr._lock:
            self._stderr._chunks.clear()
            self._stderr._size = 0
            self._stderr._truncated = False

        with self._total_lock:
            self._total_bytes = 0

    @property
    def max_bytes_per_stream(self) -> int:
        return self._stdout.max_bytes

    @property
    def total_bytes_received(self) -> int:
        with self._total_lock:
            return self._total_bytes
