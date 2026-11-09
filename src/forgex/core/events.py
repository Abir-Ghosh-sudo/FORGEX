"""Internal event system for FORGEX."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

EventHandler = Callable[["ForgexEvent"], Any]


class EventType(StrEnum):
    """Standard internal FORGEX event types."""

    APPLICATION_STARTED = "application.started"
    APPLICATION_STOPPING = "application.stopping"
    APPLICATION_STOPPED = "application.stopped"

    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    MODEL_REQUESTED = "model.requested"
    MODEL_RESPONSE = "model.response"
    MODEL_FAILED = "model.failed"

    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    FILE_CREATED = "file.created"
    FILE_MODIFIED = "file.modified"
    FILE_DELETED = "file.deleted"

    SESSION_CREATED = "session.created"
    SESSION_CLOSED = "session.closed"

    SECURITY_WARNING = "security.warning"
    PERMISSION_REQUESTED = "permission.requested"


@dataclass(slots=True, frozen=True)
class ForgexEvent:
    """Immutable event exchanged between FORGEX components."""

    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    source: str = "forgex"

    @classmethod
    def create(
        cls,
        event_type: EventType | str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "forgex",
    ) -> "ForgexEvent":
        """Create a new event."""
        return cls(
            event_type=str(event_type),
            payload=payload or {},
            source=source,
        )


class EventBus:
    """Asynchronous event dispatcher for application components."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._closed = False

    def subscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> None:
        """Register a handler for an event type."""
        if self._closed:
            raise RuntimeError("Cannot subscribe to a closed event bus.")

        key = str(event_type)

        if handler not in self._handlers[key]:
            self._handlers[key].append(handler)

    def unsubscribe(
        self,
        event_type: EventType | str,
        handler: EventHandler,
    ) -> bool:
        """Remove a registered event handler."""
        key = str(event_type)
        handlers = self._handlers.get(key)

        if not handlers or handler not in handlers:
            return False

        handlers.remove(handler)

        if not handlers:
            self._handlers.pop(key, None)

        return True

    async def publish(
        self,
        event: ForgexEvent,
        *,
        raise_errors: bool = False,
    ) -> None:
        """Publish an event to all matching handlers."""
        if self._closed:
            raise RuntimeError("Cannot publish to a closed event bus.")

        async with self._lock:
            handlers = tuple(
                self._handlers.get(event.event_type, ())
            )

        for handler in handlers:
            try:
                result = handler(event)

                if inspect.isawaitable(result):
                    await result

            except Exception:
                logger.exception(
                    "Event handler failed: event=%s handler=%r",
                    event.event_type,
                    handler,
                )

                if raise_errors:
                    raise

    async def emit(
        self,
        event_type: EventType | str,
        payload: dict[str, Any] | None = None,
        *,
        source: str = "forgex",
        raise_errors: bool = False,
    ) -> ForgexEvent:
        """Create and publish an event."""
        event = ForgexEvent.create(
            event_type,
            payload,
            source=source,
        )

        await self.publish(event, raise_errors=raise_errors)
        return event

    def listener_count(
        self,
        event_type: EventType | str | None = None,
    ) -> int:
        """Return the number of registered listeners."""
        if event_type is not None:
            return len(self._handlers.get(str(event_type), ()))

        return sum(len(handlers) for handlers in self._handlers.values())

    async def close(self) -> None:
        """Close the event bus and remove all subscriptions."""
        self._closed = True
        self._handlers.clear()


__all__ = [
    "EventBus",
    "EventHandler",
    "EventType",
    "ForgexEvent",
]