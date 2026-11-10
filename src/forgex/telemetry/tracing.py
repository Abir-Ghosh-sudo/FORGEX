
"""Execution tracing and span management for FORGEX."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import StrEnum
from time import perf_counter
from typing import Iterator
from uuid import uuid4


class SpanStatus(StrEnum):
    """Execution span status."""

    UNSET = "unset"
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class Span:
    """Represents one operation in an execution trace."""

    name: str
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_span_id: str | None = None
    status: SpanStatus = SpanStatus.RUNNING
    start_time: float = field(default_factory=perf_counter)
    end_time: float | None = None
    attributes: dict[str, str | int | float | bool] = field(
        default_factory=dict
    )
    error_type: str | None = None

    @property
    def duration_ms(self) -> float | None:
        """Return elapsed duration in milliseconds."""
        if self.end_time is None:
            return None

        return max(0.0, (self.end_time - self.start_time) * 1000)

    @property
    def is_finished(self) -> bool:
        """Check whether the span has finished."""
        return self.end_time is not None

    def set_attribute(
        self,
        key: str,
        value: str | int | float | bool,
    ) -> None:
        """Set a non-sensitive span attribute."""
        if not key or not key.strip():
            raise ValueError("Attribute key cannot be empty.")

        if isinstance(value, float):
            import math

            if not math.isfinite(value):
                raise ValueError("Attribute value must be finite.")

        self.attributes[key] = value

    def finish(
        self,
        status: SpanStatus = SpanStatus.OK,
        error_type: str | None = None,
    ) -> None:
        """Finish the span."""
        if self.is_finished:
            raise RuntimeError("Span has already finished.")

        if status in (SpanStatus.RUNNING, SpanStatus.UNSET):
            raise ValueError("A finished span needs a terminal status.")

        self.status = status
        self.error_type = error_type
        self.end_time = perf_counter()


class Tracer:
    """Thread-safe in-memory execution tracer."""

    def __init__(self, max_spans: int = 10_000) -> None:
        if max_spans < 1:
            raise ValueError("max_spans must be positive.")

        self._max_spans = max_spans
        self._spans: list[Span] = []
        self._lock = threading.RLock()

        self._current_span: ContextVar[Span | None] = ContextVar(
            f"forgex_current_span_{id(self)}",
            default=None,
        )

    @property
    def current_span(self) -> Span | None:
        """Return the current execution span."""
        return self._current_span.get()

    def start_span(
        self,
        name: str,
        attributes: dict[str, str | int | float | bool] | None = None,
        parent: Span | None = None,
    ) -> Span:
        """Create and register a new span."""
        if not name or not name.strip():
            raise ValueError("Span name cannot be empty.")

        active_parent = parent or self.current_span

        span = Span(
            name=name,
            trace_id=(
                active_parent.trace_id
                if active_parent is not None
                else str(uuid4())
            ),
            parent_span_id=(
                active_parent.span_id
                if active_parent is not None
                else None
            ),
            attributes=dict(attributes or {}),
        )

        with self._lock:
            self._spans.append(span)

            if len(self._spans) > self._max_spans:
                del self._spans[: len(self._spans) - self._max_spans]

        return span

    @contextmanager
    def span(
        self,
        name: str,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> Iterator[Span]:
        """Create a span and manage its lifecycle automatically."""
        span = self.start_span(name, attributes)
        token = self._current_span.set(span)

        try:
            yield span
        except BaseException as exc:
            span.finish(
                status=(
                    SpanStatus.CANCELLED
                    if isinstance(exc, (KeyboardInterrupt, SystemExit))
                    else SpanStatus.ERROR
                ),
                error_type=type(exc).__name__,
            )
            raise
        else:
            if not span.is_finished:
                span.finish(SpanStatus.OK)
        finally:
            self._current_span.reset(token)

    def get_spans(
        self,
        trace_id: str | None = None,
    ) -> list[Span]:
        """Return recorded spans, optionally filtered by trace ID."""
        with self._lock:
            if trace_id is None:
                return list(self._spans)

            return [
                span
                for span in self._spans
                if span.trace_id == trace_id
            ]

    def get_trace(self, trace_id: str) -> list[Span]:
        """Return all spans belonging to one trace."""
        if not trace_id:
            raise ValueError("Trace ID cannot be empty.")

        return self.get_spans(trace_id)

    def clear(self) -> None:
        """Clear recorded spans."""
        with self._lock:
            self._spans.clear()


__all__ = [
    "Span",
    "SpanStatus",
    "Tracer",
]
