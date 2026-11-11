"""Task lifecycle and progress management for FORGEX."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from forgex.core.events import EventBus, EventType
from forgex.core.exceptions import TaskCancelledError


class TaskStatus(StrEnum):
    """Possible task execution states."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class TaskProgress:
    """Tracks task execution progress."""

    percentage: float = 0.0
    current_step: str = ""
    completed_steps: int = 0
    total_steps: int = 0
    message: str = ""

    def update(
        self,
        *,
        percentage: float | None = None,
        current_step: str | None = None,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        message: str | None = None,
    ) -> None:
        """Update task progress safely."""

        if percentage is not None:
            if not 0.0 <= percentage <= 100.0:
                raise ValueError("Percentage must be between 0 and 100.")

            self.percentage = percentage

        if completed_steps is not None:
            if completed_steps < 0:
                raise ValueError("Completed steps cannot be negative.")

            self.completed_steps = completed_steps

        if total_steps is not None:
            if total_steps < 0:
                raise ValueError("Total steps cannot be negative.")

            self.total_steps = total_steps

        if self.total_steps and self.completed_steps > self.total_steps:
            raise ValueError("Completed steps cannot exceed total steps.")

        if current_step is not None:
            self.current_step = current_step

        if message is not None:
            self.message = message


@dataclass(slots=True)
class ForgexTask:
    """Represents an autonomous coding task."""

    prompt: str
    task_id: str = field(default_factory=lambda: str(uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    progress: TaskProgress = field(default_factory=TaskProgress)

    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None

    result: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    cancellation_event: asyncio.Event = field(
        default_factory=asyncio.Event,
        repr=False,
    )

    @property
    def is_terminal(self) -> bool:
        """Check whether task execution has ended."""

        return self.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }

    @property
    def duration_seconds(self) -> float | None:
        """Calculate task execution duration."""

        if self.started_at is None:
            return None

        end_time = self.completed_at or datetime.now(UTC)

        return (end_time - self.started_at).total_seconds()

    def check_cancelled(self) -> None:
        """Raise an exception when cancellation was requested."""

        if self.cancellation_event.is_set():
            raise TaskCancelledError(
                f"Task {self.task_id} was cancelled."
            )

    def request_cancellation(self) -> None:
        """Request cancellation of the task."""

        if self.is_terminal:
            raise RuntimeError(
                "Cannot cancel a task that has already finished."
            )

        self.cancellation_event.set()


class TaskManager:
    """Manages task creation, execution state and progress."""

    _ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
        TaskStatus.PENDING: {
            TaskStatus.QUEUED,
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
        },
        TaskStatus.QUEUED: {
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
        },
        TaskStatus.RUNNING: {
            TaskStatus.PAUSED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        },
        TaskStatus.PAUSED: {
            TaskStatus.RUNNING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        },
        TaskStatus.COMPLETED: set(),
        TaskStatus.FAILED: set(),
        TaskStatus.CANCELLED: set(),
    }

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self._tasks: dict[str, ForgexTask] = {}
        self._lock = asyncio.Lock()

    async def create_task(
        self,
        prompt: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> ForgexTask:
        """Create and register a new coding task."""

        normalized_prompt = prompt.strip()

        if not normalized_prompt:
            raise ValueError("Task prompt cannot be empty.")

        task = ForgexTask(
            prompt=normalized_prompt,
            metadata=dict(metadata or {}),
        )

        async with self._lock:
            self._tasks[task.task_id] = task

        await self.event_bus.emit(
            EventType.TASK_CREATED,
            {
                "task_id": task.task_id,
                "prompt": task.prompt,
                "status": task.status.value,
            },
            source="task_manager",
        )

        return task

    async def get_task(self, task_id: str) -> ForgexTask:
        """Retrieve a task by ID."""

        async with self._lock:
            task = self._tasks.get(task_id)

        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        return task

    async def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
    ) -> list[ForgexTask]:
        """Return registered tasks, optionally filtered by status."""

        async with self._lock:
            tasks = list(self._tasks.values())

        if status is not None:
            tasks = [task for task in tasks if task.status == status]

        return sorted(
            tasks,
            key=lambda task: task.created_at,
            reverse=True,
        )

    async def transition(
        self,
        task_id: str,
        new_status: TaskStatus,
    ) -> ForgexTask:
        """Change a task's execution state."""

        async with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                raise KeyError(f"Task not found: {task_id}")

            if new_status not in self._ALLOWED_TRANSITIONS[task.status]:
                raise RuntimeError(
                    f"Invalid task transition: "
                    f"{task.status.value} -> {new_status.value}"
                )

            old_status = task.status
            task.status = new_status

            now = datetime.now(UTC)

            if new_status == TaskStatus.RUNNING and task.started_at is None:
                task.started_at = now

            if new_status in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            }:
                task.completed_at = now

            if new_status == TaskStatus.COMPLETED:
                task.progress.update(percentage=100.0)

        event_mapping = {
            TaskStatus.RUNNING: EventType.TASK_STARTED,
            TaskStatus.COMPLETED: EventType.TASK_COMPLETED,
            TaskStatus.FAILED: EventType.TASK_FAILED,
            TaskStatus.CANCELLED: EventType.TASK_CANCELLED,
        }

        event_type = event_mapping.get(new_status)

        if event_type is not None:
            await self.event_bus.emit(
                event_type,
                {
                    "task_id": task.task_id,
                    "previous_status": old_status.value,
                    "status": new_status.value,
                },
                source="task_manager",
            )

        return task

    async def update_progress(
        self,
        task_id: str,
        *,
        percentage: float | None = None,
        current_step: str | None = None,
        completed_steps: int | None = None,
        total_steps: int | None = None,
        message: str | None = None,
    ) -> ForgexTask:
        """Update and publish task progress."""

        async with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                raise KeyError(f"Task not found: {task_id}")

            if task.status != TaskStatus.RUNNING:
                raise RuntimeError(
                    "Progress can only be updated for running tasks."
                )

            task.progress.update(
                percentage=percentage,
                current_step=current_step,
                completed_steps=completed_steps,
                total_steps=total_steps,
                message=message,
            )

            progress_data = {
                "task_id": task.task_id,
                "percentage": task.progress.percentage,
                "current_step": task.progress.current_step,
                "completed_steps": task.progress.completed_steps,
                "total_steps": task.progress.total_steps,
                "message": task.progress.message,
            }

        await self.event_bus.emit(
            EventType.TASK_PROGRESS,
            progress_data,
            source="task_manager",
        )

        return task

    async def complete_task(
        self,
        task_id: str,
        result: Any = None,
    ) -> ForgexTask:
        """Mark a task as successfully completed."""

        task = await self.get_task(task_id)

        async with self._lock:
            task.result = result

        return await self.transition(
            task_id,
            TaskStatus.COMPLETED,
        )

    async def fail_task(
        self,
        task_id: str,
        error: str,
    ) -> ForgexTask:
        """Mark a task as failed."""

        task = await self.get_task(task_id)

        async with self._lock:
            task.error = error

        return await self.transition(
            task_id,
            TaskStatus.FAILED,
        )

    async def cancel_task(self, task_id: str) -> ForgexTask:
        """Request and record task cancellation."""

        task = await self.get_task(task_id)

        task.request_cancellation()

        return await self.transition(
            task_id,
            TaskStatus.CANCELLED,
        )

    async def remove_task(self, task_id: str) -> bool:
        """Remove a terminal task from memory."""

        async with self._lock:
            task = self._tasks.get(task_id)

            if task is None:
                return False

            if not task.is_terminal:
                raise RuntimeError(
                    "Only completed, failed or cancelled tasks can be removed."
                )

            del self._tasks[task_id]
            return True

    async def task_count(self) -> int:
        """Return the number of registered tasks."""

        async with self._lock:
            return len(self._tasks)


__all__ = [
    "ForgexTask",
    "TaskManager",
    "TaskProgress",
    "TaskStatus",
]