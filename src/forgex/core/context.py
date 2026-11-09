"""Shared application context for FORGEX."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from forgex.core.events import EventBus

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ApplicationContext:
    """Holds shared state and services during application execution."""

    workspace: Path
    session_id: str = field(default_factory=lambda: str(uuid4()))
    event_bus: EventBus = field(default_factory=EventBus)

    started_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    metadata: dict[str, Any] = field(default_factory=dict)

    _services: dict[str, Any] = field(
        default_factory=dict,
        repr=False,
    )

    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Normalize and validate the workspace."""
        self.workspace = self.workspace.expanduser().resolve()

        if not self.workspace.exists():
            raise FileNotFoundError(
                f"Workspace does not exist: {self.workspace}"
            )

        if not self.workspace.is_dir():
            raise NotADirectoryError(
                f"Workspace is not a directory: {self.workspace}"
            )

        logger.debug(
            "Application context initialized: workspace=%s session=%s",
            self.workspace,
            self.session_id,
        )

    @property
    def closed(self) -> bool:
        """Return whether the context has been closed."""
        return self._closed

    @property
    def uptime_seconds(self) -> float:
        """Return application context uptime in seconds."""
        elapsed = datetime.now(UTC) - self.started_at
        return elapsed.total_seconds()

    def register_service(
        self,
        name: str,
        service: Any,
        *,
        replace: bool = False,
    ) -> None:
        """Register a shared application service."""
        self._ensure_open()

        normalized_name = name.strip()

        if not normalized_name:
            raise ValueError("Service name cannot be empty.")

        if normalized_name in self._services and not replace:
            raise ValueError(
                f"Service already registered: {normalized_name}"
            )

        self._services[normalized_name] = service

    def get_service(self, name: str) -> Any:
        """Retrieve a registered service."""
        self._ensure_open()

        try:
            return self._services[name]
        except KeyError as exc:
            raise LookupError(
                f"Service not registered: {name}"
            ) from exc

    def has_service(self, name: str) -> bool:
        """Check whether a service is registered."""
        return name in self._services

    def remove_service(self, name: str) -> Any | None:
        """Remove and return a registered service."""
        self._ensure_open()
        return self._services.pop(name, None)

    def set_metadata(self, key: str, value: Any) -> None:
        """Store application-level metadata."""
        self._ensure_open()

        normalized_key = key.strip()

        if not normalized_key:
            raise ValueError("Metadata key cannot be empty.")

        self.metadata[normalized_key] = value

    def get_metadata(
        self,
        key: str,
        default: Any = None,
    ) -> Any:
        """Retrieve application-level metadata."""
        return self.metadata.get(key, default)

    def _ensure_open(self) -> None:
        """Prevent operations after context shutdown."""
        if self._closed:
            raise RuntimeError("Application context is closed.")

    async def close(self) -> None:
        """Close the context and release its resources."""
        if self._closed:
            return

        self._closed = True

        await self.event_bus.close()

        for name, service in reversed(list(self._services.items())):
            close_method = getattr(service, "close", None)

            if close_method is None:
                continue

            try:
                result = close_method()

                if hasattr(result, "__await__"):
                    await result

            except Exception:
                logger.exception(
                    "Failed to close application service: %s",
                    name,
                )

        self._services.clear()
        self.metadata.clear()

        logger.debug(
            "Application context closed: session=%s",
            self.session_id,
        )


__all__ = ["ApplicationContext"]