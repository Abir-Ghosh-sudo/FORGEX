
"""FORGEX cross-platform runtime infrastructure."""

from forgex.runtime.adapters import (
    RuntimeAdapter,
    RuntimeCommand,
    create_runtime_adapter,
)
from forgex.runtime.environment import RuntimeEnvironment
from forgex.runtime.limits import (
    ResourceBudget,
    ResourceLimitError,
    ResourceLimits,
    ResourceUsage,
    recommended_limits,
)
from forgex.runtime.manager import RuntimeManager
from forgex.runtime.output import (
    OutputSnapshot,
    OutputStream,
    ProcessOutputBuffer,
)
from forgex.runtime.process import (
    ProcessExecutionError,
    ProcessManager,
    ProcessResult,
    ProcessSpec,
    ProcessStatus,
)
from forgex.runtime.process_tree import (
    ProcessTreeManager,
    TerminationResult,
    TerminationStatus,
)
from forgex.runtime.resource_manager import (
    ResourceManagerStats,
    RuntimeResourceManager,
)
from forgex.runtime.runtime_config import RuntimeConfig
from forgex.runtime.runtime_factory import (
    RuntimeComponents,
    RuntimeFactory,
)
from forgex.runtime.config_loader import (
    RuntimeConfigError,
    RuntimeConfigLoader,
)
from forgex.runtime.security import (
    ApprovalRequiredError,
    ApprovalResult,
    CommandDeniedError,
    CommandExecutionError,
    CommandRequest,
    ExecutionRecord,
    PolicyResult,
    PolicyUnavailableError,
    SecurityGateway,
    SecurityGatewayError,
)
from forgex.runtime.security_adapter import (
    RuntimeSecurityAdapter,
    SecurityAdapterError,
)
from forgex.runtime.shell import (
    ShellCommand,
    ShellManager,
    ShellType,
)
from forgex.runtime.streaming import (
    ProcessOutputStreamer,
    StreamResult,
)
from forgex.runtime.supervisor import (
    ProcessSupervisor,
    SupervisedProcessResult,
    SupervisedProcessState,
)
from forgex.runtime.supervisor_adapter import SupervisorAdapter

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
    "ResourceLimits",
    "ResourceUsage",
    "ResourceBudget",
    "ResourceLimitError",
    "recommended_limits",
    "OutputStream",
    "OutputSnapshot",
    "ProcessOutputBuffer",
    "ProcessOutputStreamer",
    "StreamResult",
    "ProcessTreeManager",
    "TerminationResult",
    "TerminationStatus",
    "RuntimeResourceManager",
    "ResourceManagerStats",
    "ProcessSupervisor",
    "SupervisedProcessResult",
    "SupervisedProcessState",
    "SupervisorAdapter",
    "RuntimeConfig",
    "RuntimeConfigLoader",
    "RuntimeConfigError",
    "RuntimeFactory",
    "RuntimeComponents",
    "SecurityGateway",
    "SecurityGatewayError",
    "PolicyUnavailableError",
    "CommandDeniedError",
    "ApprovalRequiredError",
    "CommandExecutionError",
    "CommandRequest",
    "PolicyResult",
    "ApprovalResult",
    "ExecutionRecord",
    "RuntimeSecurityAdapter",
    "SecurityAdapterError",
]
