"""Real-time subprocess output streaming for FORGEX."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from forgex.runtime.output import (
    OutputSnapshot,
    OutputStream,
    ProcessOutputBuffer,
)

logger = logging.getLogger(__name__)

OutputCallback = Callable[
    [OutputStream, str],
    None | Awaitable[None],
]


@dataclass(frozen=True, slots=True)
class StreamResult:
    """Final result of a completed output stream."""

    output: OutputSnapshot
    chunks_received: int
    callback_errors: int


class ProcessOutputStreamer:
    """Capture and optionally forward subprocess output in real time.

    This component consumes bytes from asyncio subprocess stream readers.
    It does not create or terminate subprocesses.
    """

    def __init__(
        self,
        *,
        max_bytes_per_stream: int = 1_048_576,
        chunk_size: int = 8192,
        encoding: str = "utf-8",
        callback: OutputCallback | None = None,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be positive.")

        self.buffer = ProcessOutputBuffer(
            max_bytes_per_stream=max_bytes_per_stream,
            encoding=encoding,
        )
        self.chunk_size = chunk_size
        self.encoding = encoding
        self.callback = callback

        self._chunks_received = 0
        self._callback_errors = 0
        self._counter_lock = asyncio.Lock()

    async def _forward(
        self,
        stream: OutputStream,
        data: bytes,
    ) -> None:
        """Forward a chunk to the configured callback."""

        if self.callback is None:
            return

        text = data.decode(self.encoding, errors="replace")

        try:
            result = self.callback(stream, text)

            if asyncio.iscoroutine(result) or isinstance(result, asyncio.Future):
                await result

        except asyncio.CancelledError:
            raise

        except Exception:
            async with self._counter_lock:
                self._callback_errors += 1

            logger.exception(
                "Output callback failed for stream %s.",
                stream.value,
            )

    async def _consume(
        self,
        reader: asyncio.StreamReader,
        stream: OutputStream,
    ) -> None:
        """Read one subprocess output stream until EOF."""

        while True:
            chunk = await reader.read(self.chunk_size)

            if not chunk:
                break

            self.buffer.write(stream, chunk)

            async with self._counter_lock:
                self._chunks_received += 1

            await self._forward(stream, chunk)

    async def capture(
        self,
        stdout: asyncio.StreamReader | None,
        stderr: asyncio.StreamReader | None,
    ) -> StreamResult:
        """Capture stdout and stderr concurrently until both reach EOF."""

        tasks: list[asyncio.Task[None]] = []

        try:
            if stdout is not None:
                tasks.append(
                    asyncio.create_task(
                        self._consume(stdout, OutputStream.STDOUT),
                        name="forgex-stdout-stream",
                    )
                )

            if stderr is not None:
                tasks.append(
                    asyncio.create_task(
                        self._consume(stderr, OutputStream.STDERR),
                        name="forgex-stderr-stream",
                    )
                )

            if tasks:
                await asyncio.gather(*tasks)

        except BaseException:
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        async with self._counter_lock:
            chunks = self._chunks_received
            callback_errors = self._callback_errors

        return StreamResult(
            output=self.buffer.snapshot(),
            chunks_received=chunks,
            callback_errors=callback_errors,
        )

    def snapshot(self) -> OutputSnapshot:
        """Get the currently captured output without stopping streams."""
        return self.buffer.snapshot()
