"""Metrics collection infrastructure for FORGEX."""

from __future__ import annotations

import math
import threading
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from time import time


class MetricType(StrEnum):
    """Supported metric types."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass(frozen=True, slots=True)
class Metric:
    """Immutable metric measurement."""

    name: str
    metric_type: MetricType
    value: float
    timestamp: float = field(default_factory=time)
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Metric name cannot be empty.")

        if not math.isfinite(self.value):
            raise ValueError("Metric value must be finite.")

        if not math.isfinite(self.timestamp):
            raise ValueError("Metric timestamp must be finite.")

        if self.metric_type == MetricType.COUNTER and self.value < 0:
            raise ValueError("Counter values cannot be negative.")

        normalized_labels = dict(self.labels)

        for key, value in normalized_labels.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("Metric label names must be non-empty strings.")

            if not isinstance(value, str):
                raise ValueError("Metric label values must be strings.")

        object.__setattr__(self, "labels", normalized_labels)


class MetricsCollector:
    """Thread-safe in-memory metrics collector."""

    def __init__(self, max_samples_per_metric: int = 10_000) -> None:
        if max_samples_per_metric < 1:
            raise ValueError("max_samples_per_metric must be positive.")

        self._max_samples = max_samples_per_metric
        self._metrics: dict[str, list[Metric]] = defaultdict(list)
        self._lock = threading.RLock()

    def record(
        self,
        name: str,
        value: float,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Mapping[str, str] | None = None,
    ) -> Metric:
        """Record a metric measurement."""
        metric = Metric(
            name=name,
            metric_type=metric_type,
            value=float(value),
            labels=labels or {},
        )

        with self._lock:
            samples = self._metrics[metric.name]
            samples.append(metric)

            if len(samples) > self._max_samples:
                del samples[: len(samples) - self._max_samples]

        return metric

    def increment(
        self,
        name: str,
        amount: float = 1.0,
        labels: Mapping[str, str] | None = None,
    ) -> Metric:
        """Record a counter increment."""
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("Counter increment must be finite and non-negative.")

        return self.record(
            name=name,
            value=amount,
            metric_type=MetricType.COUNTER,
            labels=labels,
        )

    def gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> Metric:
        """Record a gauge measurement."""
        return self.record(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels,
        )

    def observe(
        self,
        name: str,
        value: float,
        labels: Mapping[str, str] | None = None,
    ) -> Metric:
        """Record a histogram observation."""
        return self.record(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            labels=labels,
        )

    def get(
        self,
        name: str,
    ) -> list[Metric]:
        """Return recorded measurements for a metric."""
        with self._lock:
            return list(self._metrics.get(name, []))

    def latest(self, name: str) -> Metric | None:
        """Return the latest measurement for a metric."""
        with self._lock:
            samples = self._metrics.get(name)
            return samples[-1] if samples else None

    def count(self, name: str | None = None) -> int:
        """Return the number of recorded measurements."""
        with self._lock:
            if name is not None:
                return len(self._metrics.get(name, []))

            return sum(len(samples) for samples in self._metrics.values())

    def summary(self) -> dict[str, dict[str, float | int]]:
        """Return basic statistics for every metric."""
        with self._lock:
            result: dict[str, dict[str, float | int]] = {}

            for name, samples in self._metrics.items():
                if not samples:
                    continue

                values = [sample.value for sample in samples]

                result[name] = {
                    "count": len(values),
                    "latest": values[-1],
                    "minimum": min(values),
                    "maximum": max(values),
                    "average": sum(values) / len(values),
                }

            return result

    def clear(self, name: str | None = None) -> None:
        """Clear one metric or all collected metrics."""
        with self._lock:
            if name is None:
                self._metrics.clear()
            else:
                self._metrics.pop(name, None)


__all__ = [
    "Metric",
    "MetricType",
    "MetricsCollector",
]
