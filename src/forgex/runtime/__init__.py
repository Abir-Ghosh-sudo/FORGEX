
"""FORGEX cross-platform runtime infrastructure."""

from forgex.runtime.adapters import (
    RuntimeAdapter,
    RuntimeCommand,
    create_runtime_adapter,
)
from forgex.runtime.environment import RuntimeEnvironment
from forgex.runtime.manager import RuntimeManager
from forgex.runtime.process import (
    ProcessExecutionError,
    ProcessManager,
    ProcessResult,
    ProcessSpec,
    ProcessStatus,
)
from forgex.runtime.shell import (
    ShellCommand,
    ShellManager,
    ShellType,
)

__all__ = [
    "RuntimeEnvironment",
    "RuntimeAdapter",
    "RuntimeCommand",
    "create_runtime_adapter",
    "RuntimeManager",
    "ProcessExecutionError",
    "ProcessManager",
    "ProcessResult",
    "ProcessSpec",
    "ProcessStatus",
    "ShellCommand",
    "ShellManager",
    "ShellType",
]
