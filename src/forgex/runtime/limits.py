"""Resource limits and execution budgets for FORGEX."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResourceLimits:
    """Configurable resource limits for subprocess execution."""

    timeout_seconds: float = 120.0
    max_output_bytes: int = 1_048_576
    max_concurrent_processes: int = 4
    max_cpu_seconds: int | None = None
    max_memory_bytes: int | None = None
    max_file_size_bytes: int | None = None
    max_open_files: int | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")

        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be positive.")

        if self.max_concurrent_processes < 1:
            raise ValueError("max_concurrent_processes must be positive.")

        optional_limits = {
            "max_cpu_seconds": self.max_cpu_seconds,
            "max_memory_bytes": self.max_memory_bytes,
            "max_file_size_bytes": self.max_file_size_bytes,
            "max_open_files": self.max_open_files,
        }

        for name, value in optional_limits.items():
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive or None.")


@dataclass(frozen=True, slots=True)
class ResourceUsage:
    """Observed resource usage for a process."""

    pid: int
    cpu_seconds: float | None = None
    memory_bytes: int | None = None
    output_bytes: int = 0


class ResourceLimitError(RuntimeError):
    """Raised when a resource limit is violated."""


class ResourceBudget:
    """Track resource consumption against configured limits."""

    def __init__(self, limits: ResourceLimits) -> None:
        self.limits = limits
        self._active_processes = 0
        self._total_output_bytes = 0

    @property
    def active_processes(self) -> int:
        return self._active_processes

    @property
    def total_output_bytes(self) -> int:
        return self._total_output_bytes

    def acquire_process(self) -> None:
        """Reserve one process execution slot."""

        if self._active_processes >= self.limits.max_concurrent_processes:
            raise ResourceLimitError("Maximum concurrent process limit reached.")

        self._active_processes += 1

    def release_process(self) -> None:
        """Release one process execution slot."""

        if self._active_processes <= 0:
            raise RuntimeError("No active process slot to release.")

        self._active_processes -= 1

    def record_output(self, byte_count: int) -> None:
        """Record output bytes produced by running processes."""

        if byte_count < 0:
            raise ValueError("byte_count cannot be negative.")

        self._total_output_bytes += byte_count

        if self._total_output_bytes > self.limits.max_output_bytes:
            raise ResourceLimitError("Aggregate process output limit exceeded.")

    def check_usage(self, usage: ResourceUsage) -> None:
        """Check observed resource usage against configured limits."""

        if usage.output_bytes < 0:
            raise ValueError("output_bytes cannot be negative.")

        if usage.cpu_seconds is not None:
            if usage.cpu_seconds < 0:
                raise ValueError("cpu_seconds cannot be negative.")

            maximum = self.limits.max_cpu_seconds

            if maximum is not None and usage.cpu_seconds > maximum:
                raise ResourceLimitError(f"CPU time limit exceeded for PID {usage.pid}.")

        if usage.memory_bytes is not None:
            if usage.memory_bytes < 0:
                raise ValueError("memory_bytes cannot be negative.")

            maximum = self.limits.max_memory_bytes

            if maximum is not None and usage.memory_bytes > maximum:
                raise ResourceLimitError(f"Memory limit exceeded for PID {usage.pid}.")

        if usage.output_bytes > self.limits.max_output_bytes:
            raise ResourceLimitError(f"Output limit exceeded for PID {usage.pid}.")

    def reset_output(self) -> None:
        """Reset aggregate output accounting."""
        self._total_output_bytes = 0


def recommended_limits(
    *,
    available_memory_bytes: int | None = None,
    cpu_count: int | None = None,
) -> ResourceLimits:
    """Create conservative defaults based on available hardware."""

    if cpu_count is None:
        cpu_count = os.cpu_count() or 2

    if cpu_count < 1:
        cpu_count = 2

    concurrency = min(max(cpu_count // 2, 1), 4)

    memory_limit: int | None = None

    if available_memory_bytes is not None:
        if available_memory_bytes <= 0:
            raise ValueError("available_memory_bytes must be positive.")

        # Reserve at least half of available memory for FORGEX and OS.
        memory_limit = max(
            available_memory_bytes // 4,
            256 * 1024 * 1024,
        )

    return ResourceLimits(
        timeout_seconds=120.0,
        max_output_bytes=1_048_576,
        max_concurrent_processes=concurrency,
        max_cpu_seconds=120,
        max_memory_bytes=memory_limit,
    )
