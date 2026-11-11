"""FORGEX tool system.

Provides filesystem, terminal, Git, testing, and package-management tools.
"""

from forgex.tools.filesystem import FilesystemToolkit
from forgex.tools.git import (
    GitOperations,
    GitRemoteOperations,
    GitRepositoryManager,
)
from forgex.tools.packages import PackageToolkit
from forgex.tools.terminal import (
    SupervisorTerminalRunner,
    TerminalExecutor,
)
from forgex.tools.testing import TestingToolkit

__all__ = [
    "FilesystemToolkit",
    "GitOperations",
    "GitRemoteOperations",
    "GitRepositoryManager",
    "PackageToolkit",
    "SupervisorTerminalRunner",
    "TerminalExecutor",
    "TestingToolkit",
]