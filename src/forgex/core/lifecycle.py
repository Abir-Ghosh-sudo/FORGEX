"""Application lifecycle management for FORGEX."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from forgex.core.context import ApplicationContext
from forgex.core.events import EventType
from forgex.core.exceptions import InitializationError

logger = logging.getLogger(__name__)

LifecycleHook = Callable[
    [ApplicationContext],
    Awaitable[None] | None,
]


class ApplicationState(StrEnum):
    """Application lifecycle states."""

    CREATED = "created"
    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class ApplicationLifecycle:
    """Controls the startup and shutdown lifecycle of FORGEX."""

    def __init__(self, context: ApplicationContext) -> None:
        self.context = context
        self._state = ApplicationState.CREATED
        self._startup_hooks: list[LifecycleHook] = []
        self._shutdown_hooks: list[LifecycleHook] = []
        self._lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()

    @property
    def state(self) -> ApplicationState:
        """Return the current application state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check whether the application is running."""
        return self._state == ApplicationState.RUNNING

    def add_startup_hook(self, hook: LifecycleHook) -> None:
        """Register an asynchronous or synchronous startup hook."""
        if self._state != ApplicationState.CREATED:
            raise RuntimeError("Startup hooks cannot be added after initialization.")

        self._startup_hooks.append(hook)

    def add_shutdown_hook(self, hook: LifecycleHook) -> None:
        """Register an asynchronous or synchronous shutdown hook."""
        if self._state in {
            ApplicationState.STOPPING,
            ApplicationState.STOPPED,
        }:
            raise RuntimeError("Shutdown hooks cannot be added during shutdown.")

        self._shutdown_hooks.append(hook)

    async def _execute_hook(self, hook: LifecycleHook) -> None:
        """Execute a lifecycle hook."""
        result = hook(self.context)

        if asyncio.iscoroutine(result) or isinstance(
            result,
            Awaitable,
        ):
            await result

    async def startup(self) -> None:
        """Initialize application services and enter running state."""
        async with self._lock:
            if self._state == ApplicationState.RUNNING:
                return

            if self._state != ApplicationState.CREATED:
                raise InitializationError(f"Cannot start application from state: {self._state}")

            if self.context.closed:
                self._state = ApplicationState.FAILED
                raise InitializationError("Cannot start with a closed application context.")

            self._state = ApplicationState.INITIALIZING

            try:
                for hook in self._startup_hooks:
                    await self._execute_hook(hook)

                await self.context.event_bus.emit(
                    EventType.APPLICATION_STARTED,
                    {
                        "session_id": self.context.session_id,
                        "workspace": str(self.context.workspace),
                    },
                    source="lifecycle",
                )

                self._state = ApplicationState.RUNNING

                logger.info(
                    "FORGEX application started. Workspace: %s",
                    self.context.workspace,
                )

            except Exception as exc:
                self._state = ApplicationState.FAILED
                logger.exception("FORGEX startup failed.")

                try:
                    await self.context.close()
                except Exception:
                    logger.exception("Failed to clean up after startup failure.")

                raise InitializationError(f"Application startup failed: {exc}") from exc

    async def shutdown(self) -> None:
        """Gracefully stop application services."""
        async with self._lock:
            if self._state == ApplicationState.STOPPED:
                return

            if self._state == ApplicationState.STOPPING:
                return

            if self._state == ApplicationState.CREATED:
                self._state = ApplicationState.STOPPED
                await self.context.close()
                self._shutdown_event.set()
                return

            self._state = ApplicationState.STOPPING

            try:
                if not self.context.closed:
                    await self.context.event_bus.emit(
                        EventType.APPLICATION_STOPPING,
                        {"session_id": self.context.session_id},
                        source="lifecycle",
                    )

                for hook in reversed(self._shutdown_hooks):
                    try:
                        await self._execute_hook(hook)
                    except Exception:
                        logger.exception(
                            "Application shutdown hook failed: %r",
                            hook,
                        )

                await self.context.close()

                self._state = ApplicationState.STOPPED

                logger.info("FORGEX application stopped.")

            finally:
                self._shutdown_event.set()

    async def wait_for_shutdown(self) -> None:
        """Wait until application shutdown is complete."""
        await self._shutdown_event.wait()

    async def __aenter__(self) -> ApplicationLifecycle:
        """Start the application using an async context manager."""
        await self.startup()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        """Shut down the application when leaving the context."""
        await self.shutdown()


__all__ = [
    "ApplicationLifecycle",
    "ApplicationState",
    "LifecycleHook",
]
