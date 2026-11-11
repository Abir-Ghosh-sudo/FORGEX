"""Unit tests for FORGEX permission management."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

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

TEST_WORKSPACE = Path(".").resolve()


@pytest.fixture
def manager() -> PermissionManager:
    return PermissionManager()


@pytest.fixture
def basic_request() -> PermissionRequest:
    return PermissionRequest(
        subject="agent:coder",
        resource="src/main.py",
        action=PermissionLevel.READ,
        workspace=TEST_WORKSPACE,
        risk=RiskLevel.LOW,
    )


class TestPermissionEnums:
    def test_permission_actions_exist(self) -> None:
        assert PermissionAction.ALLOW.value == "allow"
        assert PermissionAction.DENY.value == "deny"
        assert PermissionAction.ASK.value == "ask"

    def test_permission_levels_exist(self) -> None:
        assert PermissionLevel.READ.value == "read"
        assert PermissionLevel.WRITE.value == "write"
        assert PermissionLevel.EXECUTE.value == "execute"
        assert len(PermissionLevel) > 0

    def test_risk_levels_exist(self) -> None:
        assert len(RiskLevel) > 0

    def test_permission_scopes_exist(self) -> None:
        assert len(PermissionScope) > 0


class TestPermissionRequest:
    def test_request_creation(self, basic_request: PermissionRequest) -> None:
        assert basic_request.subject == "agent:coder"
        assert basic_request.resource == "src/main.py"
        assert basic_request.action == PermissionLevel.READ

    def test_empty_subject_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PermissionRequest(
                subject="",
                resource="src/main.py",
                action=PermissionLevel.READ,
                workspace=TEST_WORKSPACE,
                risk=RiskLevel.LOW,
            )

    def test_empty_resource_rejected(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            PermissionRequest(
                subject="agent:coder",
                resource="",
                action=PermissionLevel.READ,
                workspace=TEST_WORKSPACE,
                risk=RiskLevel.LOW,
            )


def _make_grant(
    subject: str = "agent:coder",
    resource_pattern: str = "src/*",
    level: PermissionLevel = PermissionLevel.READ,
    scope: PermissionScope = PermissionScope.WORKSPACE,
    expires_in: timedelta | None = None,
    workspace: Path | None = TEST_WORKSPACE,
) -> PermissionGrant:
    now = datetime.now(timezone.utc)
    return PermissionGrant(
        grant_id="test-grant",
        subject=subject,
        resource_pattern=resource_pattern,
        level=level,
        scope=scope,
        workspace=workspace,
        created_at=now,
        expires_at=(
            now + expires_in if expires_in is not None else None
        ),
    )


class TestPermissionGrant:
    def test_grant_creation(self) -> None:
        grant = _make_grant()

        assert grant.subject == "agent:coder"
        assert grant.level == PermissionLevel.READ
        assert not grant.is_expired()

    def test_grant_expiry(self) -> None:
        grant = _make_grant(expires_in=timedelta(seconds=-1))
        assert grant.is_expired()


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
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        assert len(manager.list_grants()) >= 1

    def test_matching_grant_allows_request(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )
        decision = manager.check(basic_request)

        assert decision.allowed is True

    def test_wrong_subject_does_not_match(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:reviewer",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        assert manager.check(basic_request).allowed is False

    def test_wrong_action_does_not_match(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.WRITE,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        assert manager.check(basic_request).allowed is False

    def test_wrong_resource_does_not_match(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:coder",
            resource_pattern="tests/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        assert manager.check(basic_request).allowed is False

    def test_revoke_grant(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        grants = manager.list_grants()
        grant_id = grants[0].grant_id
        manager.revoke(grant_id)

        assert manager.check(basic_request).allowed is False

    def test_expired_grant_does_not_allow(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )

        assert manager.check(basic_request).allowed is False

    def test_future_grant_allows(
        self,
        manager: PermissionManager,
        basic_request: PermissionRequest,
    ) -> None:
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )

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
        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

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
                    subject=f"agent:{index}",
                    resource_pattern="src/*",
                    level=PermissionLevel.READ,
                    scope=PermissionScope.WORKSPACE,
                    workspace=TEST_WORKSPACE,
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
            subject="agent:reviewer",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        assert manager.check(basic_request).allowed is False

    def test_workspace_scope_does_not_allow_unrelated_resource(
        self,
        manager: PermissionManager,
    ) -> None:
        request = PermissionRequest(
            subject="agent:coder",
            resource="../outside/secret.txt",
            action=PermissionLevel.READ,
            workspace=TEST_WORKSPACE,
            risk=RiskLevel.LOW,
        )

        manager.grant(
            subject="agent:coder",
            resource_pattern="src/*",
            level=PermissionLevel.READ,
            scope=PermissionScope.WORKSPACE,
            workspace=TEST_WORKSPACE,
        )

        assert manager.check(request).allowed is False


class TestPermissionDecision:
    def test_allow_decision(self) -> None:
        d = PermissionDecision.allow("granted")
        assert d.allowed is True
        assert d.action == PermissionAction.ALLOW

    def test_deny_decision(self) -> None:
        d = PermissionDecision.deny("denied")
        assert d.allowed is False
        assert d.action == PermissionAction.DENY

    def test_ask_decision(self) -> None:
        d = PermissionDecision.ask("needs approval")
        assert d.allowed is False
        assert d.action == PermissionAction.ASK
