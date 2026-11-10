
"""Integration tests for FORGEX telemetry components."""

from forgex.telemetry import (
    MetricType,
    MetricsCollector,
    SpanStatus,
    TelemetryEvent,
    TelemetryEventType,
    Tracer,
)


def test_telemetry_event_and_metrics_work_together():
    collector = MetricsCollector()

    event = TelemetryEvent(
        event_type=TelemetryEventType.TASK_COMPLETED,
        component="orchestrator",
        duration_ms=120.5,
        success=True,
    )

    collector.increment(
        "tasks.completed",
        labels={"component": event.component},
    )
    collector.observe(
        "tasks.duration",
        event.duration_ms,
    )

    assert event.success is True
    assert collector.count() == 2
    assert collector.latest("tasks.completed").value == 1


def test_tracing_and_metrics_work_together():
    tracer = Tracer()
    collector = MetricsCollector()

    with tracer.span("agent.execute") as span:
        span.set_attribute("agent", "coder")

    assert span.status == SpanStatus.OK
    assert span.duration_ms is not None

    collector.observe(
        "agent.execution.duration",
        span.duration_ms,
    )

    assert collector.latest("agent.execution.duration") is not None


def test_complete_telemetry_workflow():
    tracer = Tracer()
    collector = MetricsCollector()

    with tracer.span("task.execute") as task_span:
        with tracer.span("agent.code") as agent_span:
            agent_span.set_attribute("agent", "coder")

        collector.increment("agent.completed")
        collector.observe(
            "agent.duration",
            agent_span.duration_ms,
        )

    event = TelemetryEvent(
        event_type=TelemetryEventType.TASK_COMPLETED,
        component="orchestrator",
        duration_ms=task_span.duration_ms,
        success=True,
    )

    assert event.success is True
    assert task_span.status == SpanStatus.OK
    assert agent_span.status == SpanStatus.OK
    assert collector.count() == 2

    trace = tracer.get_trace(task_span.trace_id)

    assert len(trace) == 2


def test_telemetry_metric_types():
    collector = MetricsCollector()

    collector.increment("requests", 3)
    collector.gauge("memory.usage", 512)
    collector.observe("execution.duration", 50)

    assert collector.latest("requests").metric_type == MetricType.COUNTER
    assert collector.latest("memory.usage").metric_type == MetricType.GAUGE
    assert collector.latest("execution.duration").metric_type == MetricType.HISTOGRAM


def test_telemetry_data_serialization():
    event = TelemetryEvent(
        event_type=TelemetryEventType.TOOL_COMPLETED,
        component="terminal",
        success=True,
    )

    serialized = event.model_dump(mode="json")

    assert serialized["event_type"] == "tool.completed"
    assert serialized["component"] == "terminal"
    assert serialized["success"] is True
