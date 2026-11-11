
"""Benchmark result models for FORGEX engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class BenchmarkResult:
    name: str
    iterations: int
    total_seconds: float
    average_seconds: float
    minimum_seconds: float
    maximum_seconds: float
    operations_per_second: float
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BenchmarkReport:
    started_at: datetime
    completed_at: datetime
    results: list[BenchmarkResult] = field(default_factory=list)
    environment: dict[str, Any] = field(default_factory=dict)

    @property
    def total_benchmarks(self) -> int:
        return len(self.results)

    @property
    def successful(self) -> int:
        return sum(result.success for result in self.results)

    @property
    def failed(self) -> int:
        return self.total_benchmarks - self.successful

    @property
    def total_duration(self) -> float:
        return sum(result.total_seconds for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "total_benchmarks": self.total_benchmarks,
            "successful": self.successful,
            "failed": self.failed,
            "total_duration": self.total_duration,
            "environment": self.environment,
            "results": [
                result.to_dict() for result in self.results
            ],
        }
