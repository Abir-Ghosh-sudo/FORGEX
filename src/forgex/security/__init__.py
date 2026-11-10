
"""FORGEX security package.

Central exports for permissions, policies, approvals,
sandbox execution, secret detection and security auditing.
"""

from .approvals import (
    ApprovalManager,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
    ApprovalToken,
)
from .audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    AuditOutcome,
    AuditRecord,
    AuditVerificationResult,
)
from .permissions import (
    PermissionAction,
    PermissionDecision,
    PermissionGrant,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    PermissionScope,
    RiskLevel,
)
from .policy import (
    OperationType,
    PolicyMode,
    SecurityEvaluation,
    SecurityPolicy,
    SecurityPolicyConfig,
    SecurityRule,
)
from .sandbox import (
    FilesystemOperation,
    SandboxConfig,
    SandboxError,
    SandboxExecutionResult,
    SandboxLimits,
    SandboxManager,
)
from .secrets import (
    RedactionResult,
    SecretMatch,
    SecretPattern,
    SecretScanner,
    SecretType,
    redact_secrets,
)

__all__ = [
    # Permissions
    "PermissionAction",
    "PermissionDecision",
    "PermissionGrant",
    "PermissionLevel",
    "PermissionManager",
    "PermissionRequest",
    "PermissionScope",
    "RiskLevel",

    # Security policy
    "OperationType",
    "PolicyMode",
    "SecurityEvaluation",
    "SecurityPolicy",
    "SecurityPolicyConfig",
    "SecurityRule",

    # Approvals
    "ApprovalManager",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalStatus",
    "ApprovalToken",

    # Sandbox
    "FilesystemOperation",
    "SandboxConfig",
    "SandboxError",
    "SandboxExecutionResult",
    "SandboxLimits",
    "SandboxManager",

    # Secret detection
    "RedactionResult",
    "SecretMatch",
    "SecretPattern",
    "SecretScanner",
    "SecretType",
    "redact_secrets",

    # Audit
    "AuditEvent",
    "AuditEventType",
    "AuditLogger",
    "AuditOutcome",
    "AuditRecord",
    "AuditVerificationResult",
]
