

"""Unit tests for FORGEX telemetry metrics."""

import math
import threading

import pytest

from forgex.telemetry.metrics import (
    Metric,
    MetricType,
    MetricsCollector,
)


def test_create_metric():
    metric = Metric(
        name="task.count",
        metric_type=MetricType.COUNTER,
        value=5,
    )

    assert metric.name == "task.count"
    assert metric.value == 5
    assert metric.metric_type == MetricType.COUNTER


def test_metric_rejects_empty_name():
    with pytest.raises(ValueError):
        Metric(name=" ", metric_type=MetricType.GAUGE, value=1)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_metric_rejects_non_finite_values(value):
    with pytest.raises(ValueError):
        Metric(name="cpu.usage", metric_type=MetricType.GAUGE, value=value)


def test_counter_rejects_negative_value():
    with pytest.raises(ValueError):
        Metric(name="requests", metric_type=MetricType.COUNTER, value=-1)


def test_metric_labels_are_copied():
    labels = {"component": "agent"}
    metric = Metric(
        name="agent.calls",
        metric_type=MetricType.COUNTER,
        value=1,
        labels=labels,
    )

    labels["component"] = "changed"

    assert metric.labels["component"] == "agent"


def test_collector_increment():
    collector = MetricsCollector()

    collector.increment("task.completed")
    collector.increment("task.completed", 2)

    assert collector.count("task.completed") == 2
    assert collector.summary()["task.completed"]["latest"] == 2


def test_collector_gauge():
    collector = MetricsCollector()

    metric = collector.gauge("memory.usage", 512)

    assert metric.metric_type == MetricType.GAUGE
    assert metric.value == 512


def test_collector_histogram():
    collector = MetricsCollector()

    collector.observe("execution.duration", 10)
    collector.observe("execution.duration", 20)
    collector.observe("execution.duration", 30)

    summary = collector.summary()["execution.duration"]

    assert summary["count"] == 3
    assert summary["minimum"] == 10
    assert summary["maximum"] == 30
    assert summary["average"] == 20


def test_collector_latest():
    collector = MetricsCollector()

    collector.gauge("cpu", 20)
    collector.gauge("cpu", 40)

    assert collector.latest("cpu").value == 40


def test_collector_bounded_samples():
    collector = MetricsCollector(max_samples_per_metric=3)

    for value in range(5):
        collector.gauge("temperature", value)

    assert collector.count("temperature") == 3
    assert [m.value for m in collector.get("temperature")] == [2, 3, 4]


def test_collector_clear_single_metric():
    collector = MetricsCollector()

    collector.gauge("cpu", 10)
    collector.gauge("memory", 20)

    collector.clear("cpu")

    assert collector.latest("cpu") is None
    assert collector.latest("memory").value == 20


def test_collector_clear_all():
    collector = MetricsCollector()

    collector.gauge("cpu", 10)
    collector.increment("requests")

    collector.clear()

    assert collector.count() == 0
    assert collector.summary() == {}


def test_increment_rejects_negative_amount():
    collector = MetricsCollector()

    with pytest.raises(ValueError):
        collector.increment("requests", -1)


def test_increment_rejects_non_finite_amount():
    collector = MetricsCollector()

    with pytest.raises(ValueError):
        collector.increment("requests", math.inf)


def test_collector_rejects_zero_capacity():
    with pytest.raises(ValueError):
        MetricsCollector(max_samples_per_metric=0)


def test_collector_thread_safety():
    collector = MetricsCollector()

    def record_metrics():
        for _ in range(100):
            collector.increment("concurrent.requests")

    threads = [
        threading.Thread(target=record_metrics)
        for _ in range(5)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    assert collector.count("concurrent.requests") == 500
    assert collector.summary()["concurrent.requests"]["average"] == 1
