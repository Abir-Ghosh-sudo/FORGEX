"""FORGEX Git integration package.

Provides safe Git operations, branch management, commit/rollback,
and recovery for FORGEX autonomous workflows.
"""

from forgex.git.manager import GitManager, GitOperationResult
from forgex.git.safety import GitSafetyChecker

__all__ = ["GitManager", "GitOperationResult", "GitSafetyChecker"]
