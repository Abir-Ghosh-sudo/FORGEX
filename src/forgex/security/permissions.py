"""Permission management and authorization policies for FORGEX."""

from __future__ import annotations

import fnmatch
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import uuid4


class PermissionAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class PermissionLevel(StrEnum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    ADMIN = "admin"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionScope(StrEnum):
    GLOBAL = "global"
    WORKSPACE = "workspace"
    RESOURCE = "resource"


@dataclass(frozen=True, slots=True)
class PermissionRequest:
    """Represents a request to perform a protected operation."""

    subject: str
    resource: str
    action: PermissionLevel
    workspace: Path | None = None
    risk: RiskLevel = RiskLevel.MEDIUM
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise ValueError("Permission subject cannot be empty.")

        if not self.resource.strip():
            raise ValueError("Permission resource cannot be empty.")

        if self.workspace is not None:
            object.__setattr__(
                self,
                "workspace",
                self.workspace.expanduser().resolve(strict=False),
            )


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    """An explicit permission grant with optional expiration."""

    grant_id: str
    subject: str
    resource_pattern: str
    level: PermissionLevel
    scope: PermissionScope
    workspace: Path | None
    created_at: datetime
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.grant_id.strip():
            raise ValueError("Grant ID cannot be empty.")

        if not self.subject.strip():
            raise ValueError("Grant subject cannot be empty.")

        if not self.resource_pattern.strip():
            raise ValueError("Resource pattern cannot be empty.")

        if self.created_at.tzinfo is None:
            raise ValueError("Grant creation time must be timezone-aware.")

        if self.expires_at is not None and self.expires_at.tzinfo is None:
            raise ValueError("Grant expiration time must be timezone-aware.")

        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("Grant expiration must be after creation.")

        if self.scope == PermissionScope.WORKSPACE and self.workspace is None:
            raise ValueError("Workspace-scoped grants require a workspace.")

        if self.workspace is not None:
            object.__setattr__(
                self,
                "workspace",
                self.workspace.expanduser().resolve(strict=False),
            )

    def is_expired(self, now: datetime | None = None) -> bool:
        """Return whether this grant has expired."""

        if self.expires_at is None:
            return False

        current = now or datetime.now(UTC)

        if current.tzinfo is None:
            raise ValueError("Current time must be timezone-aware.")

        return current >= self.expires_at


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    """Result of a permission evaluation."""

    action: PermissionAction
    allowed: bool
    reason: str
    grant_id: str | None = None

    @classmethod
    def allow(
        cls,
        reason: str,
        grant_id: str | None = None,
    ) -> PermissionDecision:
        return cls(
            action=PermissionAction.ALLOW,
            allowed=True,
            reason=reason,
            grant_id=grant_id,
        )

    @classmethod
    def deny(cls, reason: str) -> PermissionDecision:
        return cls(
            action=PermissionAction.DENY,
            allowed=False,
            reason=reason,
        )

    @classmethod
    def ask(cls, reason: str) -> PermissionDecision:
        return cls(
            action=PermissionAction.ASK,
            allowed=False,
            reason=reason,
        )


class PermissionManager:
    """Thread-safe permission manager using explicit grants.

    Default behavior is deny-by-default.

    A grant only authorizes operations at or below its permission level.
    Critical-risk operations always require interactive approval.
    """

    _LEVEL_RANK: dict[PermissionLevel, int] = {
        PermissionLevel.NONE: 0,
        PermissionLevel.READ: 1,
        PermissionLevel.WRITE: 2,
        PermissionLevel.EXECUTE: 3,
        PermissionLevel.ADMIN: 4,
    }

    def __init__(
        self,
        *,
        default_action: PermissionAction = PermissionAction.DENY,
        require_approval_for: Iterable[RiskLevel] | None = None,
    ) -> None:
        self._default_action = default_action
        self._approval_risks = frozenset(
            require_approval_for
            if require_approval_for is not None
            else {RiskLevel.HIGH, RiskLevel.CRITICAL}
        )

        self._grants: dict[str, PermissionGrant] = {}
        self._revoked: set[str] = set()
        self._lock = threading.RLock()

    def grant(
        self,
        *,
        subject: str,
        resource_pattern: str,
        level: PermissionLevel,
        scope: PermissionScope = PermissionScope.RESOURCE,
        workspace: Path | None = None,
        expires_in: timedelta | None = None,
    ) -> PermissionGrant:
        """Create and register a permission grant."""

        if not subject.strip():
            raise ValueError("Subject cannot be empty.")

        if not resource_pattern.strip():
            raise ValueError("Resource pattern cannot be empty.")

        if level == PermissionLevel.NONE:
            raise ValueError("Cannot grant NONE permission.")

        if expires_in is not None and expires_in <= timedelta(0):
            raise ValueError("Grant expiration duration must be positive.")

        if scope == PermissionScope.GLOBAL and workspace is not None:
            raise ValueError("Global grants cannot specify a workspace.")

        if scope == PermissionScope.WORKSPACE and workspace is None:
            raise ValueError("Workspace grants require a workspace.")

        now = datetime.now(UTC)

        grant = PermissionGrant(
            grant_id=str(uuid4()),
            subject=subject,
            resource_pattern=resource_pattern,
            level=level,
            scope=scope,
            workspace=(
                workspace.expanduser().resolve(strict=False) if workspace is not None else None
            ),
            created_at=now,
            expires_at=(now + expires_in if expires_in is not None else None),
        )

        with self._lock:
            self._grants[grant.grant_id] = grant

        return grant

    def revoke(self, grant_id: str) -> bool:
        """Revoke an existing grant. Returns False if it does not exist."""

        with self._lock:
            if grant_id not in self._grants:
                return False

            self._revoked.add(grant_id)
            return True

    def revoke_subject(self, subject: str) -> int:
        """Revoke all active grants belonging to a subject."""

        with self._lock:
            grant_ids = [
                grant_id
                for grant_id, grant in self._grants.items()
                if grant.subject == subject and grant_id not in self._revoked
            ]

            self._revoked.update(grant_ids)
            return len(grant_ids)

    def get_grant(self, grant_id: str) -> PermissionGrant | None:
        """Retrieve a grant unless it has been revoked."""

        with self._lock:
            if grant_id in self._revoked:
                return None

            grant = self._grants.get(grant_id)

            if grant is None or grant.is_expired():
                return None

            return grant

    def list_grants(
        self,
        *,
        subject: str | None = None,
        include_expired: bool = False,
        include_revoked: bool = False,
    ) -> list[PermissionGrant]:
        """Return a snapshot of registered grants."""

        now = datetime.now(UTC)

        with self._lock:
            result = []

            for grant_id, grant in self._grants.items():
                if subject is not None and grant.subject != subject:
                    continue

                if not include_revoked and grant_id in self._revoked:
                    continue

                if not include_expired and grant.is_expired(now):
                    continue

                result.append(grant)

            return result

    def check(self, request: PermissionRequest) -> PermissionDecision:
        """Evaluate a permission request."""

        if request.action == PermissionLevel.NONE:
            return PermissionDecision.deny("NONE-level operations cannot be authorized.")

        if request.risk == RiskLevel.CRITICAL:
            return PermissionDecision.ask(
                "Critical-risk operations always require explicit approval."
            )

        if request.risk in self._approval_risks:
            return PermissionDecision.ask(
                f"{request.risk.value.capitalize()}-risk operation requires approval."
            )

        with self._lock:
            candidates = [
                grant
                for grant_id, grant in self._grants.items()
                if grant_id not in self._revoked
                and not grant.is_expired()
                and self._matches(grant, request)
            ]

        if not candidates:
            if self._default_action == PermissionAction.ASK:
                return PermissionDecision.ask("No matching permission grant exists.")

            return PermissionDecision.deny("No matching permission grant exists. Access denied.")

        candidates.sort(
            key=lambda grant: (
                self._LEVEL_RANK[grant.level],
                grant.created_at,
            ),
            reverse=True,
        )

        selected = candidates[0]

        if self._LEVEL_RANK[selected.level] < self._LEVEL_RANK[request.action]:
            return PermissionDecision.deny(
                "The available grant does not authorize this permission level."
            )

        return PermissionDecision.allow(
            "Operation authorized by an explicit permission grant.",
            grant_id=selected.grant_id,
        )

    def _matches(
        self,
        grant: PermissionGrant,
        request: PermissionRequest,
    ) -> bool:
        """Check whether a grant matches a permission request."""

        if grant.subject not in {"*", request.subject}:
            return False

        if not fnmatch.fnmatchcase(request.resource, grant.resource_pattern):
            return False

        if grant.scope == PermissionScope.GLOBAL:
            return True

        if grant.scope == PermissionScope.WORKSPACE:
            if request.workspace is None or grant.workspace is None:
                return False

            try:
                request.workspace.relative_to(grant.workspace)
                return True
            except ValueError:
                return False

        return grant.scope == PermissionScope.RESOURCE

    def clear(self) -> None:
        """Remove all grants and revocation records."""

        with self._lock:
            self._grants.clear()
            self._revoked.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._grants) - len(self._revoked)
