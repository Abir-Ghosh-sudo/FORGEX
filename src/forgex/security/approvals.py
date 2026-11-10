
"""Human-in-the-loop approval management for FORGEX."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Final
from uuid import uuid4


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class ApprovalError(Exception):
    """Base exception for approval operations."""


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval request does not exist."""


class ApprovalExpiredError(ApprovalError):
    """Raised when an approval request has expired."""


class ApprovalAlreadyResolvedError(ApprovalError):
    """Raised when a resolved request is modified."""


class ApprovalTokenError(ApprovalError):
    """Raised when an approval token is invalid or already consumed."""


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """An immutable request for human authorization."""

    request_id: str
    subject: str
    operation: str
    resource: str
    reason: str
    created_at: datetime
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "subject", "operation", "resource", "reason"):
            value = getattr(self, name)

            if not value.strip():
                raise ValueError(f"{name} cannot be empty.")

        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("Approval timestamps must be timezone-aware.")

        if self.expires_at <= self.created_at:
            raise ValueError("Approval expiration must follow creation time.")

        if self.resolved_at is not None and self.resolved_at.tzinfo is None:
            raise ValueError("Resolution timestamp must be timezone-aware.")

        if self.status == ApprovalStatus.PENDING and self.resolved_at is not None:
            raise ValueError("Pending requests cannot have a resolution timestamp.")


@dataclass(frozen=True, slots=True)
class ApprovalToken:
    """A one-time token bound to a specific approved operation."""

    token_id: str
    request_id: str
    subject: str
    operation: str
    resource: str
    expires_at: datetime
    _secret_hash: str

    def __repr__(self) -> str:
        return (
            "ApprovalToken("
            f"token_id={self.token_id!r}, "
            f"request_id={self.request_id!r}, "
            "secret=[REDACTED])"
        )


@dataclass(frozen=True, slots=True)
class ApprovalResult:
    """Result of an approval operation."""

    request: ApprovalRequest
    token: ApprovalToken | None = None


class ApprovalManager:
    """Thread-safe approval lifecycle and one-time token manager.

    Important:
        Approval tokens are in-memory capabilities. They are not durable
        across process restarts and must never be logged or exposed publicly.
    """

    _DEFAULT_TIMEOUT: Final[timedelta] = timedelta(minutes=5)

    def __init__(
        self,
        *,
        default_timeout: timedelta = _DEFAULT_TIMEOUT,
        token_timeout: timedelta = timedelta(minutes=1),
    ) -> None:
        if default_timeout <= timedelta(0):
            raise ValueError("Default timeout must be positive.")

        if token_timeout <= timedelta(0):
            raise ValueError("Token timeout must be positive.")

        self._default_timeout = default_timeout
        self._token_timeout = token_timeout

        self._requests: dict[str, ApprovalRequest] = {}
        self._tokens: dict[str, ApprovalToken] = {}
        self._consumed_tokens: set[str] = set()

        self._lock = threading.RLock()

    def create_request(
        self,
        *,
        subject: str,
        operation: str,
        resource: str,
        reason: str,
        timeout: timedelta | None = None,
    ) -> ApprovalRequest:
        """Create a pending approval request."""

        duration = timeout or self._default_timeout

        if duration <= timedelta(0):
            raise ValueError("Approval timeout must be positive.")

        now = datetime.now(UTC)

        request = ApprovalRequest(
            request_id=str(uuid4()),
            subject=subject,
            operation=operation,
            resource=resource,
            reason=reason,
            created_at=now,
            expires_at=now + duration,
        )

        with self._lock:
            self._requests[request.request_id] = request

        return request

    def approve(
        self,
        request_id: str,
        *,
        approved_by: str,
    ) -> ApprovalResult:
        """Approve a request and issue a one-time capability token."""

        if not approved_by.strip():
            raise ValueError("Approver identity cannot be empty.")

        with self._lock:
            request = self._get_active_request(request_id)
            now = datetime.now(UTC)

            token = self._issue_token(request, now)

            updated = ApprovalRequest(
                request_id=request.request_id,
                subject=request.subject,
                operation=request.operation,
                resource=request.resource,
                reason=request.reason,
                created_at=request.created_at,
                expires_at=request.expires_at,
                status=ApprovalStatus.APPROVED,
                resolved_at=now,
                resolved_by=approved_by,
            )

            self._requests[request_id] = updated

            return ApprovalResult(
                request=updated,
                token=token,
            )

    def reject(
        self,
        request_id: str,
        *,
        rejected_by: str,
        reason: str = "",
    ) -> ApprovalRequest:
        """Reject a pending request."""

        if not rejected_by.strip():
            raise ValueError("Rejector identity cannot be empty.")

        with self._lock:
            request = self._get_active_request(request_id)

            updated = ApprovalRequest(
                request_id=request.request_id,
                subject=request.subject,
                operation=request.operation,
                resource=request.resource,
                reason=request.reason,
                created_at=request.created_at,
                expires_at=request.expires_at,
                status=ApprovalStatus.REJECTED,
                resolved_at=datetime.now(UTC),
                resolved_by=rejected_by,
                rejection_reason=reason or None,
            )

            self._requests[request_id] = updated
            return updated

    def consume_token(
        self,
        token: ApprovalToken,
        *,
        subject: str,
        operation: str,
        resource: str,
    ) -> bool:
        """Consume a token once after validating its exact operation binding.

        Returns True only when the token authorizes this exact operation.
        """

        with self._lock:
            stored = self._tokens.get(token.token_id)

            if stored is None:
                raise ApprovalTokenError("Unknown approval token.")

            if token.token_id in self._consumed_tokens:
                raise ApprovalTokenError("Approval token has already been consumed.")

            if not hmac.compare_digest(
                stored._secret_hash,
                token._secret_hash,
            ):
                raise ApprovalTokenError("Approval token integrity check failed.")

            if stored != token:
                raise ApprovalTokenError("Approval token does not match stored token.")

            if stored.expires_at <= datetime.now(UTC):
                self._tokens.pop(token.token_id, None)
                raise ApprovalExpiredError("Approval token has expired.")

            if (
                stored.subject != subject
                or stored.operation != operation
                or stored.resource != resource
            ):
                raise ApprovalTokenError(
                    "Approval token is not authorized for this operation."
                )

            request = self._requests.get(stored.request_id)

            if request is None or request.status != ApprovalStatus.APPROVED:
                raise ApprovalTokenError("Associated approval is no longer valid.")

            self._consumed_tokens.add(token.token_id)
            self._tokens.pop(token.token_id, None)

            self._requests[request.request_id] = ApprovalRequest(
                request_id=request.request_id,
                subject=request.subject,
                operation=request.operation,
                resource=request.resource,
                reason=request.reason,
                created_at=request.created_at,
                expires_at=request.expires_at,
                status=ApprovalStatus.CONSUMED,
                resolved_at=request.resolved_at,
                resolved_by=request.resolved_by,
            )

            return True

    def get_request(self, request_id: str) -> ApprovalRequest:
        """Get a request, updating its status if it has expired."""

        with self._lock:
            request = self._requests.get(request_id)

            if request is None:
                raise ApprovalNotFoundError(
                    f"Approval request not found: {request_id}"
                )

            if (
                request.status == ApprovalStatus.PENDING
                and request.expires_at <= datetime.now(UTC)
            ):
                request = self._expire_request(request)

            return request

    def list_requests(
        self,
        *,
        status: ApprovalStatus | None = None,
        subject: str | None = None,
    ) -> list[ApprovalRequest]:
        """Return a snapshot of approval requests."""

        with self._lock:
            results = []

            for request_id in list(self._requests):
                request = self._requests[request_id]

                if (
                    request.status == ApprovalStatus.PENDING
                    and request.expires_at <= datetime.now(UTC)
                ):
                    request = self._expire_request(request)

                if status is not None and request.status != status:
                    continue

                if subject is not None and request.subject != subject:
                    continue

                results.append(request)

            return results

    def cleanup(self) -> int:
        """Remove expired requests and obsolete tokens."""

        now = datetime.now(UTC)
        removed = 0

        with self._lock:
            for request_id, request in list(self._requests.items()):
                if (
                    request.status == ApprovalStatus.PENDING
                    and request.expires_at <= now
                ):
                    self._expire_request(request)

            for token_id, token in list(self._tokens.items()):
                if token.expires_at <= now:
                    self._tokens.pop(token_id, None)
                    removed += 1

            return removed

    def _get_active_request(self, request_id: str) -> ApprovalRequest:
        request = self._requests.get(request_id)

        if request is None:
            raise ApprovalNotFoundError(
                f"Approval request not found: {request_id}"
            )

        if request.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(
                f"Request is already {request.status.value}."
            )

        if request.expires_at <= datetime.now(UTC):
            self._expire_request(request)
            raise ApprovalExpiredError("Approval request has expired.")

        return request

    def _expire_request(self, request: ApprovalRequest) -> ApprovalRequest:
        """Transition a pending request into the expired state."""

        updated = ApprovalRequest(
            request_id=request.request_id,
            subject=request.subject,
            operation=request.operation,
            resource=request.resource,
            reason=request.reason,
            created_at=request.created_at,
            expires_at=request.expires_at,
            status=ApprovalStatus.EXPIRED,
            resolved_at=datetime.now(UTC),
        )

        self._requests[request.request_id] = updated
        return updated

    def _issue_token(
        self,
        request: ApprovalRequest,
        now: datetime,
    ) -> ApprovalToken:
        """Create a cryptographically random one-time token."""

        secret = secrets.token_urlsafe(32)
        token_id = str(uuid4())

        secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

        # The secret is held only in this token object.
        # Its hash is stored separately for integrity verification.
        token = ApprovalToken(
            token_id=token_id,
            request_id=request.request_id,
            subject=request.subject,
            operation=request.operation,
            resource=request.resource,
            expires_at=min(
                request.expires_at,
                now + self._token_timeout,
            ),
            _secret_hash=secret_hash,
        )

        # Keep the actual secret out of repr and normal logs.
        self._tokens[token_id] = token

        return token

    def __len__(self) -> int:
        with self._lock:
            return len(self._requests)
