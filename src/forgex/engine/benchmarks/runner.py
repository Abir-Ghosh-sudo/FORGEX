
"""Benchmark execution engine."""

from __future__ import annotations

import platform
import statistics
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .models import BenchmarkReport, BenchmarkResult


class BenchmarkRunner:
    """Runs repeatable synchronous benchmarks."""

    def __init__(
        self,
        *,
        warmup_iterations: int = 2,
        default_iterations: int = 10,
    ) -> None:
        if warmup_iterations < 0:
            raise ValueError("warmup_iterations cannot be negative")

        if default_iterations < 1:
            raise ValueError("default_iterations must be positive")

        self.warmup_iterations = warmup_iterations
        self.default_iterations = default_iterations

        self._results: list[BenchmarkResult] = []

    def run(
        self,
        name: str,
        operation: Callable[[], Any],
        *,
        iterations: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> BenchmarkResult:
        """Execute one benchmark."""

        count = iterations or self.default_iterations

        if count < 1:
            raise ValueError("iterations must be positive")

        if not callable(operation):
            raise TypeError("operation must be callable")

        try:
            for _ in range(self.warmup_iterations):
                operation()

            timings: list[float] = []

            for _ in range(count):
                started = time.perf_counter()
                operation()
                elapsed = time.perf_counter() - started
                timings.append(elapsed)

            total = sum(timings)
            average = statistics.mean(timings)

            result = BenchmarkResult(
                name=name,
                iterations=count,
                total_seconds=total,
                average_seconds=average,
                minimum_seconds=min(timings),
                maximum_seconds=max(timings),
                operations_per_second=(
                    count / total if total > 0 else 0.0
                ),
                metadata=metadata or {},
            )

        except Exception as exc:
            result = BenchmarkResult(
                name=name,
                iterations=count,
                total_seconds=0.0,
                average_seconds=0.0,
                minimum_seconds=0.0,
                maximum_seconds=0.0,
                operations_per_second=0.0,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
                metadata=metadata or {},
            )

        self._results.append(result)
        return result

    def create_report(self) -> BenchmarkReport:
        """Create a report from completed benchmarks."""

        now = datetime.now(UTC)

        return BenchmarkReport(
            started_at=now,
            completed_at=now,
            results=list(self._results),
            environment={
                "python": sys.version,
                "implementation": platform.python_implementation(),
                "platform": platform.platform(),
                "machine": platform.machine(),
                "processor": platform.processor(),
            },
        )

    def clear(self) -> None:
        self._results.clear()

    @property
    def results(self) -> tuple[BenchmarkResult, ...]:
        return tuple(self._results)
