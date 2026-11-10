
"""Tests for FORGEX human-in-the-loop approval management."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from forgex.security.approvals import (
    ApprovalAlreadyResolvedError,
    ApprovalExpiredError,
    ApprovalManager,
    ApprovalNotFoundError,
    ApprovalStatus,
    ApprovalToken,
    ApprovalTokenError,
)


@pytest.fixture
def manager() -> ApprovalManager:
    return ApprovalManager(
        default_timeout=timedelta(minutes=5),
        token_timeout=timedelta(minutes=1),
    )


@pytest.fixture
def approval_request(manager: ApprovalManager):
    return manager.create_request(
        subject="user-123",
        operation="filesystem.write",
        resource="src/main.py",
        reason="Update application code",
    )


@pytest.fixture
def approved(manager: ApprovalManager, approval_request):
    return manager.approve(
        approval_request.request_id,
        approved_by="admin-123",
    )


class TestRequestCreation:

    def test_create_request(self, manager: ApprovalManager) -> None:
        result = manager.create_request(
            subject="user-1",
            operation="filesystem.write",
            resource="src/main.py",
            reason="Update source",
        )

        assert result.status == ApprovalStatus.PENDING
        assert result.subject == "user-1"
        assert result.expires_at > result.created_at

    def test_request_has_unique_id(self, manager: ApprovalManager) -> None:
        kwargs = {
            "subject": "user-1",
            "operation": "filesystem.read",
            "resource": "README.md",
            "reason": "Read project documentation",
        }

        first = manager.create_request(**kwargs)
        second = manager.create_request(**kwargs)

        assert first.request_id != second.request_id

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("subject", ""),
            ("operation", ""),
            ("resource", ""),
            ("reason", ""),
            ("subject", "   "),
        ],
    )
    def test_reject_invalid_required_fields(
        self,
        manager: ApprovalManager,
        field: str,
        value: str,
    ) -> None:
        kwargs = {
            "subject": "user",
            "operation": "filesystem.write",
            "resource": "file.py",
            "reason": "Test",
        }
        kwargs[field] = value

        with pytest.raises(ValueError):
            manager.create_request(**kwargs)

    def test_reject_non_positive_timeout(
        self,
        manager: ApprovalManager,
    ) -> None:
        with pytest.raises(ValueError):
            manager.create_request(
                subject="user",
                operation="filesystem.write",
                resource="file.py",
                reason="Test",
                timeout=timedelta(0),
            )

    def test_reject_negative_timeout(
        self,
        manager: ApprovalManager,
    ) -> None:
        with pytest.raises(ValueError):
            manager.create_request(
                subject="user",
                operation="filesystem.write",
                resource="file.py",
                reason="Test",
                timeout=timedelta(seconds=-1),
            )


class TestApprovalLifecycle:

    def test_approve_request(self, approved) -> None:
        assert approved.request.status == ApprovalStatus.APPROVED
        assert approved.request.resolved_by == "admin-123"
        assert approved.request.resolved_at is not None
        assert approved.token is not None

    def test_approve_creates_token(self, approved) -> None:
        assert approved.token is not None
        assert approved.token.secret
        assert approved.token.token_id

    def test_token_repr_hides_secret(self, approved) -> None:
        token = approved.token

        assert token is not None
        assert token.secret not in repr(token)
        assert "[REDACTED]" in repr(token)

    def test_reject_request(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        result = manager.reject(
            approval_request.request_id,
            rejected_by="admin-123",
            reason="Not permitted",
        )

        assert result.status == ApprovalStatus.REJECTED
        assert result.rejection_reason == "Not permitted"
        assert result.resolved_by == "admin-123"
        assert result.resolved_at is not None

    def test_cannot_approve_twice(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        manager.approve(
            approval_request.request_id,
            approved_by="admin",
        )

        with pytest.raises(ApprovalAlreadyResolvedError):
            manager.approve(
                approval_request.request_id,
                approved_by="admin",
            )

    def test_cannot_reject_approved_request(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        manager.approve(
            approval_request.request_id,
            approved_by="admin",
        )

        with pytest.raises(ApprovalAlreadyResolvedError):
            manager.reject(
                approval_request.request_id,
                rejected_by="admin",
            )

    def test_cannot_approve_unknown_request(
        self,
        manager: ApprovalManager,
    ) -> None:
        with pytest.raises(ApprovalNotFoundError):
            manager.approve(
                "unknown-request",
                approved_by="admin",
            )

    def test_reject_empty_approver(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        with pytest.raises(ValueError):
            manager.approve(
                approval_request.request_id,
                approved_by=" ",
            )

    def test_reject_empty_rejector(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        with pytest.raises(ValueError):
            manager.reject(
                approval_request.request_id,
                rejected_by=" ",
            )


class TestTokenConsumption:

    def test_consume_valid_token(self, manager, approved) -> None:
        assert manager.consume_token(
            approved.token,
            subject="user-123",
            operation="filesystem.write",
            resource="src/main.py",
        )

    def test_consumed_request_status(
        self,
        manager,
        approved,
    ) -> None:
        manager.consume_token(
            approved.token,
            subject="user-123",
            operation="filesystem.write",
            resource="src/main.py",
        )

        result = manager.get_request(approved.request.request_id)

        assert result.status == ApprovalStatus.CONSUMED

    def test_token_cannot_be_consumed_twice(
        self,
        manager,
        approved,
    ) -> None:
        kwargs = {
            "subject": "user-123",
            "operation": "filesystem.write",
            "resource": "src/main.py",
        }

        manager.consume_token(approved.token, **kwargs)

        with pytest.raises(ApprovalTokenError):
            manager.consume_token(approved.token, **kwargs)

    @pytest.mark.parametrize(
        ("subject", "operation", "resource"),
        [
            ("another-user", "filesystem.write", "src/main.py"),
            ("user-123", "filesystem.delete", "src/main.py"),
            ("user-123", "filesystem.write", "src/other.py"),
        ],
    )
    def test_wrong_operation_binding_rejected(
        self,
        manager,
        approved,
        subject: str,
        operation: str,
        resource: str,
    ) -> None:
        with pytest.raises(ApprovalTokenError):
            manager.consume_token(
                approved.token,
                subject=subject,
                operation=operation,
                resource=resource,
            )

    def test_wrong_binding_does_not_consume_token(
        self,
        manager,
        approved,
    ) -> None:
        with pytest.raises(ApprovalTokenError):
            manager.consume_token(
                approved.token,
                subject="wrong-user",
                operation="filesystem.write",
                resource="src/main.py",
            )

        assert manager.consume_token(
            approved.token,
            subject="user-123",
            operation="filesystem.write",
            resource="src/main.py",
        )

    def test_unknown_token_rejected(
        self,
        manager: ApprovalManager,
    ) -> None:
        token = ApprovalToken(
            token_id="unknown",
            request_id="unknown",
            subject="user",
            operation="filesystem.write",
            resource="file.py",
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
            secret="random-secret",
        )

        with pytest.raises(ApprovalTokenError):
            manager.consume_token(
                token,
                subject="user",
                operation="filesystem.write",
                resource="file.py",
            )

    def test_forged_secret_rejected(
        self,
        manager,
        approved,
    ) -> None:
        original = approved.token

        forged = ApprovalToken(
            token_id=original.token_id,
            request_id=original.request_id,
            subject=original.subject,
            operation=original.operation,
            resource=original.resource,
            expires_at=original.expires_at,
            secret="forged-secret",
        )

        with pytest.raises(ApprovalTokenError):
            manager.consume_token(
                forged,
                subject="user-123",
                operation="filesystem.write",
                resource="src/main.py",
            )

        # A forged token must not invalidate the original capability.
        assert manager.consume_token(
            original,
            subject="user-123",
            operation="filesystem.write",
            resource="src/main.py",
        )

    def test_modified_token_metadata_rejected(
        self,
        manager,
        approved,
    ) -> None:
        original = approved.token

        modified = ApprovalToken(
            token_id=original.token_id,
            request_id=original.request_id,
            subject=original.subject,
            operation=original.operation,
            resource="different.py",
            expires_at=original.expires_at,
            secret=original.secret,
        )

        with pytest.raises(ApprovalTokenError):
            manager.consume_token(
                modified,
                subject="user-123",
                operation="filesystem.write",
                resource="different.py",
            )

    def test_invalid_token_type_rejected(
        self,
        manager: ApprovalManager,
    ) -> None:
        with pytest.raises(ApprovalTokenError):
            manager.consume_token(
                "not-a-token",
                subject="user",
                operation="filesystem.write",
                resource="file.py",
            )


class TestExpiration:

    def test_expired_request(
        self,
        manager: ApprovalManager,
    ) -> None:
        created = manager.create_request(
            subject="user",
            operation="filesystem.write",
            resource="file.py",
            reason="Test expiration",
            timeout=timedelta(milliseconds=1),
        )

        time.sleep(0.02)

        result = manager.get_request(created.request_id)

        assert result.status == ApprovalStatus.EXPIRED

    def test_cannot_approve_expired_request(
        self,
        manager: ApprovalManager,
    ) -> None:
        created = manager.create_request(
            subject="user",
            operation="filesystem.write",
            resource="file.py",
            reason="Test expiration",
            timeout=timedelta(milliseconds=1),
        )

        time.sleep(0.02)

        with pytest.raises(ApprovalExpiredError):
            manager.approve(
                created.request_id,
                approved_by="admin",
            )

    def test_expired_token(self) -> None:
        manager = ApprovalManager(
            token_timeout=timedelta(milliseconds=1),
        )

        created = manager.create_request(
            subject="user",
            operation="filesystem.write",
            resource="file.py",
            reason="Test token expiry",
        )

        result = manager.approve(
            created.request_id,
            approved_by="admin",
        )

        time.sleep(0.02)

        with pytest.raises(ApprovalExpiredError):
            manager.consume_token(
                result.token,
                subject="user",
                operation="filesystem.write",
                resource="file.py",
            )


class TestListingAndCleanup:

    def test_get_request(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        result = manager.get_request(approval_request.request_id)

        assert result.request_id == approval_request.request_id

    def test_unknown_request_raises(
        self,
        manager: ApprovalManager,
    ) -> None:
        with pytest.raises(ApprovalNotFoundError):
            manager.get_request("missing")

    def test_list_requests(self, manager: ApprovalManager) -> None:
        for index in range(3):
            manager.create_request(
                subject=f"user-{index}",
                operation="filesystem.read",
                resource="README.md",
                reason="Test listing",
            )

        assert len(manager.list_requests()) == 3

    def test_filter_by_status(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        manager.approve(
            approval_request.request_id,
            approved_by="admin",
        )

        results = manager.list_requests(
            status=ApprovalStatus.APPROVED,
        )

        assert len(results) == 1

    def test_filter_by_subject(
        self,
        manager: ApprovalManager,
    ) -> None:
        manager.create_request(
            subject="alice",
            operation="filesystem.read",
            resource="README.md",
            reason="Test",
        )
        manager.create_request(
            subject="bob",
            operation="filesystem.read",
            resource="README.md",
            reason="Test",
        )

        results = manager.list_requests(subject="alice")

        assert len(results) == 1
        assert results[0].subject == "alice"

    def test_cleanup_removes_expired_token(self) -> None:
        manager = ApprovalManager(
            token_timeout=timedelta(milliseconds=1),
        )

        created = manager.create_request(
            subject="user",
            operation="filesystem.write",
            resource="file.py",
            reason="Cleanup test",
        )

        manager.approve(
            created.request_id,
            approved_by="admin",
        )

        time.sleep(0.02)

        assert manager.cleanup() == 1

    def test_manager_length(
        self,
        manager: ApprovalManager,
        approval_request,
    ) -> None:
        assert len(manager) == 1


class TestConcurrentConsumption:

    def test_only_one_thread_can_consume_token(
        self,
        manager,
        approved,
    ) -> None:
        barrier = threading.Barrier(2)

        def consume() -> str:
            barrier.wait()

            try:
                manager.consume_token(
                    approved.token,
                    subject="user-123",
                    operation="filesystem.write",
                    resource="src/main.py",
                )
                return "success"
            except ApprovalTokenError:
                return "rejected"

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(lambda _: consume(), range(2))
            )

        assert results.count("success") == 1
        assert results.count("rejected") == 1
