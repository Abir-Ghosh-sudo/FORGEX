
"""Unit tests for FORGEX telemetry events."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from forgex.telemetry.events import (
    TelemetryEvent,
    TelemetryEventType,
)


def test_create_telemetry_event():
    event = TelemetryEvent(
        event_type=TelemetryEventType.TASK_STARTED,
        component="orchestrator",
    )

    assert event.event_type == TelemetryEventType.TASK_STARTED
    assert event.component == "orchestrator"
    assert event.event_id
    assert event.timestamp.tzinfo is not None


def test_event_generates_unique_ids():
    first = TelemetryEvent(
        event_type=TelemetryEventType.TASK_STARTED,
        component="core",
    )
    second = TelemetryEvent(
        event_type=TelemetryEventType.TASK_STARTED,
        component="core",
    )

    assert first.event_id != second.event_id


def test_event_accepts_optional_metadata():
    event = TelemetryEvent(
        event_type=TelemetryEventType.TASK_COMPLETED,
        component="orchestrator",
        operation="execute",
        duration_ms=125.5,
        success=True,
        attributes={"agent_count": 3},
    )

    assert event.operation == "execute"
    assert event.duration_ms == 125.5
    assert event.success is True
    assert event.attributes["agent_count"] == 3


def test_event_normalizes_timestamp_to_utc():
    event = TelemetryEvent(
        event_type=TelemetryEventType.APPLICATION_STARTED,
        component="application",
        timestamp=datetime.now(timezone.utc),
    )

    assert event.timestamp.utcoffset().total_seconds() == 0


def test_event_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        TelemetryEvent(
            event_type=TelemetryEventType.TASK_STARTED,
            component="core",
            timestamp=datetime.now(),
        )


@pytest.mark.parametrize("duration", [-1, -0.1])
def test_event_rejects_negative_duration(duration):
    with pytest.raises(ValidationError):
        TelemetryEvent(
            event_type=TelemetryEventType.TASK_COMPLETED,
            component="core",
            duration_ms=duration,
        )


def test_event_rejects_empty_component():
    with pytest.raises(ValidationError):
        TelemetryEvent(
            event_type=TelemetryEventType.TASK_STARTED,
            component=" ",
        )


def test_event_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TelemetryEvent(
            event_type=TelemetryEventType.TASK_STARTED,
            component="core",
            secret="should-not-be-accepted",
        )


def test_event_serialization():
    event = TelemetryEvent(
        event_type=TelemetryEventType.TOOL_COMPLETED,
        component="terminal",
        operation="execute",
        success=True,
    )

    data = event.model_dump(mode="json")

    assert data["event_type"] == "tool.completed"
    assert data["component"] == "terminal"
    assert data["success"] is True


def test_event_rejects_negative_infinite_duration():
    with pytest.raises(ValidationError):
        TelemetryEvent(
            event_type=TelemetryEventType.TASK_COMPLETED,
            component="core",
            duration_ms=float("-inf"),
        )
