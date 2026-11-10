
"""Unit tests for FORGEX telemetry tracing."""

import time

import pytest

from forgex.telemetry.tracing import (
    Span,
    SpanStatus,
    Tracer,
)


def test_create_span():
    span = Span(name="agent.execute")

    assert span.name == "agent.execute"
    assert span.status == SpanStatus.RUNNING
    assert span.trace_id
    assert span.span_id
    assert not span.is_finished


def test_span_duration():
    span = Span(name="operation")

    time.sleep(0.01)
    span.finish()

    assert span.duration_ms >= 5
    assert span.is_finished


def test_span_finish_status():
    span = Span(name="operation")
    span.finish(SpanStatus.OK)

    assert span.status == SpanStatus.OK


def test_span_rejects_double_finish():
    span = Span(name="operation")
    span.finish()

    with pytest.raises(RuntimeError):
        span.finish()


def test_span_rejects_non_terminal_status():
    span = Span(name="operation")

    with pytest.raises(ValueError):
        span.finish(SpanStatus.RUNNING)


def test_span_attributes():
    span = Span(name="agent.execute")

    span.set_attribute("agent", "coder")
    span.set_attribute("attempt", 2)

    assert span.attributes["agent"] == "coder"
    assert span.attributes["attempt"] == 2


def test_span_rejects_empty_attribute_key():
    span = Span(name="operation")

    with pytest.raises(ValueError):
        span.set_attribute(" ", "value")


def test_tracer_start_span():
    tracer = Tracer()

    span = tracer.start_span("task.execute")

    assert span.name == "task.execute"
    assert len(tracer.get_spans()) == 1


def test_tracer_context_manager():
    tracer = Tracer()

    with tracer.span("task.execute") as span:
        assert tracer.current_span is span
        assert span.status == SpanStatus.RUNNING

    assert span.status == SpanStatus.OK
    assert span.is_finished
    assert tracer.current_span is None


def test_tracer_records_exception():
    tracer = Tracer()

    with pytest.raises(ValueError):
        with tracer.span("task.execute") as span:
            raise ValueError("Test error")

    assert span.status == SpanStatus.ERROR
    assert span.error_type == "ValueError"
    assert span.is_finished


def test_nested_spans_share_trace_id():
    tracer = Tracer()

    with tracer.span("parent") as parent:
        with tracer.span("child") as child:
            assert child.parent_span_id == parent.span_id
            assert child.trace_id == parent.trace_id

    assert len(tracer.get_trace(parent.trace_id)) == 2


def test_explicit_parent_span():
    tracer = Tracer()

    parent = tracer.start_span("parent")
    child = tracer.start_span("child", parent=parent)

    assert child.parent_span_id == parent.span_id
    assert child.trace_id == parent.trace_id


def test_tracer_filters_by_trace_id():
    tracer = Tracer()

    first = tracer.start_span("first")
    tracer.start_span("second")

    assert tracer.get_spans(first.trace_id) == [first]


def test_tracer_bounded_storage():
    tracer = Tracer(max_spans=2)

    first = tracer.start_span("first")
    second = tracer.start_span("second")
    third = tracer.start_span("third")

    spans = tracer.get_spans()

    assert len(spans) == 2
    assert first not in spans
    assert second in spans
    assert third in spans


def test_tracer_clear():
    tracer = Tracer()

    tracer.start_span("operation")
    tracer.clear()

    assert tracer.get_spans() == []


def test_tracer_rejects_zero_capacity():
    with pytest.raises(ValueError):
        Tracer(max_spans=0)


def test_tracer_rejects_empty_span_name():
    tracer = Tracer()

    with pytest.raises(ValueError):
        tracer.start_span(" ")


def test_finished_span_has_no_duration_before_finish():
    span = Span(name="operation")

    assert span.duration_ms is None


def test_tracer_preserves_context_after_exception():
    tracer = Tracer()

    with tracer.span("outer") as outer:
        with pytest.raises(RuntimeError):
            with tracer.span("inner"):
                raise RuntimeError("Expected")

        assert tracer.current_span is outer

    assert tracer.current_span is None

