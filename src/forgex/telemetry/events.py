"""Privacy-conscious telemetry event models for FORGEX."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelemetryEventType(StrEnum):
    """Supported telemetry event categories."""

    APPLICATION_STARTED = "application.started"
    APPLICATION_STOPPED = "application.stopped"

    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"

    MODEL_REQUESTED = "model.requested"
    MODEL_COMPLETED = "model.completed"
    MODEL_FAILED = "model.failed"

    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    TOOL_FAILED = "tool.failed"

    SESSION_CREATED = "session.created"
    SESSION_COMPLETED = "session.completed"

    SECURITY_BLOCKED = "security.blocked"
    VERIFICATION_COMPLETED = "verification.completed"


class TelemetryEvent(BaseModel):
    """A structured telemetry event without sensitive source content."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=False,
    )

    event_id: str = Field(
        default_factory=lambda: str(uuid4()),
        min_length=1,
        max_length=64,
    )

    event_type: TelemetryEventType

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    component: str = Field(
        min_length=1,
        max_length=100,
    )

    operation: str | None = Field(
        default=None,
        max_length=100,
    )

    duration_ms: float | None = Field(
        default=None,
        ge=0,
    )

    success: bool | None = None

    error_type: str | None = Field(
        default=None,
        max_length=100,
    )

    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """Ensure timestamps are timezone-aware and normalized to UTC."""
        if value.tzinfo is None:
            raise ValueError("Telemetry timestamps must be timezone-aware.")

        return value.astimezone(timezone.utc)

    @field_validator("component", "operation", "error_type")
    @classmethod
    def reject_empty_strings(cls, value: str | None) -> str | None:
        """Reject blank metadata values."""
        if value is not None and not value.strip():
            raise ValueError("Telemetry metadata cannot be empty.")

        return value


__all__ = [
    "TelemetryEvent",
    "TelemetryEventType",
]