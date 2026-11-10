
"""Unit tests for FORGEX permission management."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from forgex.security.permissions import (
    PermissionAction,
    PermissionDecision,
    PermissionGrant,
    PermissionLevel,
    PermissionManager,
    PermissionRequest,
    PermissionScope,
    RiskLevel,
)


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def basic_request() -> PermissionRequest:
    return PermissionRequest(
        subject="agent:coder",
        action=PermissionAction.READ,
        resource="src/main.py",
        scope=PermissionScope.WORKSPACE,
        risk_level=RiskLevel.LOW,
    )


class TestPermissionEnums:
    def test_permission_actions_exist(self) -> None:
        assert PermissionAction.READ.value == "read"
        assert PermissionAction.WRITE.value == "write"
        assert PermissionAction.EXECUTE.value == "execute"

    def test_permission_levels_exist(self) -> None:
        assert len(PermissionLevel) > 0

    def test_risk_levels_exist(self) -> None:
        assert len(RiskLevel) > 0

    def test_permission_scopes_exist(self) -> None:
        assert len(PermissionScope) > 0


class TestPermissionRequest:
    def test_request_creation(self, basic_request: PermissionRequest) -> None:
        assert basic_request.subject == "agent:coder"
        assert basic_request.resource == "src/main.py"

    def test_empty_subject_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PermissionRequest(
                subject="",
                action=PermissionAction.READ,
                resource="src/main.py",
                scope=PermissionScope.WORKSPACE,
                risk_level=RiskLevel.LOW,
            )

    def test_empty_resource_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PermissionRequest(
                subject="agent:coder",
                action=PermissionAction.READ,
                resource="",
                scope=PermissionScope.WORKSPACE,
                risk_level=RiskLevel.LOW,
            )


class TestPermissionGrant:
    def test_grant_creation(self) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        assert grant.subject == "agent:coder"
        assert grant.action == PermissionAction.READ

    def test_grant_expiry(self) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
            expires_at=expires_at,
        )

        assert grant.expires_at == expires_at


class TestPermissionManager:
    def test_default_deny(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        decision = manager.check(basic_request)

        assert decision.allowed is False

    def test_add_grant(
        self,
        manager: PermissionManager,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        manager.grant(grant)

        assert len(manager.list_grants()) >= 1

    def test_matching_grant_allows_request(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        manager.grant(grant)
        decision = manager.check(basic_request)

        assert decision.allowed is True

    def test_wrong_subject_does_not_match(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:reviewer",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        manager.grant(grant)

        assert manager.check(basic_request).allowed is False

    def test_wrong_action_does_not_match(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.WRITE,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        manager.grant(grant)

        assert manager.check(basic_request).allowed is False

    def test_wrong_resource_does_not_match(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="tests/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        manager.grant(grant)

        assert manager.check(basic_request).allowed is False

    def test_revoke_grant(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        grant_id = manager.grant(grant)
        manager.revoke(grant_id)

        assert manager.check(basic_request).allowed is False

    def test_expired_grant_does_not_allow(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )

        manager.grant(grant)

        assert manager.check(basic_request).allowed is False

    def test_future_grant_allows(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

        manager.grant(grant)

        assert manager.check(basic_request).allowed is True

    def test_revoke_unknown_grant(
        self,
        manager: PermissionManager,
    ) -> None:
        result = manager.revoke("unknown-grant-id")

        assert result is False


class TestPermissionConcurrency:
    def test_concurrent_permission_checks(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        grant = PermissionGrant(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="src/*",
            scope=PermissionScope.WORKSPACE,
            level=PermissionLevel.ALLOW,
        )

        manager.grant(grant)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda _: manager.check(basic_request).allowed,
                    range(100),
                )
            )

        assert all(results)

    def test_concurrent_grant_operations(
        self,
        manager: PermissionManager,
    ) -> None:
        errors: list[Exception] = []
        lock = threading.Lock()

        def add_grant(index: int) -> None:
            try:
                manager.grant(
                    PermissionGrant(
                        subject=f"agent:{index}",
                        action=PermissionAction.READ,
                        resource="src/*",
                        scope=PermissionScope.WORKSPACE,
                        level=PermissionLevel.ALLOW,
                    )
                )
            except Exception as exc:
                with lock:
                    errors.append(exc)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(add_grant, range(50)))

        assert not errors
        assert len(manager.list_grants()) >= 50


class TestPermissionIsolation:
    def test_different_subjects_are_isolated(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            PermissionGrant(
                subject="agent:reviewer",
                action=PermissionAction.READ,
                resource="src/*",
                scope=PermissionScope.WORKSPACE,
                level=PermissionLevel.ALLOW,
            )
        )

        assert manager.check(basic_request).allowed is False

    def test_workspace_scope_does_not_allow_unrelated_resource(
        self,
        manager: PermissionManager,
    ) -> None:
        request = PermissionRequest(
            subject="agent:coder",
            action=PermissionAction.READ,
            resource="../outside/secret.txt",
            scope=PermissionScope.WORKSPACE,
            risk_level=RiskLevel.LOW,
        )

        manager.grant(
            PermissionGrant(
                subject="agent:coder",
                action=PermissionAction.READ,
                resource="src/*",
                scope=PermissionScope.WORKSPACE,
                level=PermissionLevel.ALLOW,
            )
        )

        assert manager.check(request).allowed is False
