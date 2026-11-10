
"""Unit tests for FORGEX security policy command inspection."""

import pytest

from forgex.security.permissions import PermissionManager, RiskLevel
from forgex.security.policy import SecurityPolicy


@pytest.fixture
def policy() -> SecurityPolicy:
    """Create a security policy for command inspection tests."""
    return SecurityPolicy(PermissionManager())


@pytest.mark.parametrize(
    ("command", "expected_risk", "expected_reason"),
    [
        (
            'powershell -Command "Remove-Item important.txt"',
            RiskLevel.CRITICAL,
            "Nested destructive command detected.",
        ),
        (
            "powershell -EncodedCommand SGVsbG8=",
            RiskLevel.CRITICAL,
            "Encoded shell commands are not permitted.",
        ),
    ],
)
def test_critical_commands_are_rejected(
    policy: SecurityPolicy,
    command: str,
    expected_risk: RiskLevel,
    expected_reason: str,
) -> None:
    """Dangerous nested and encoded commands must be rejected."""
    result = policy.inspect_command(command)

    assert result is not None
    risk, reason = result

    assert risk == expected_risk
    assert reason == expected_reason


def test_safe_command_returns_none(policy: SecurityPolicy) -> None:
    """A normal command should not trigger a security warning."""
    assert policy.inspect_command("echo hello") is None


@pytest.mark.parametrize(
    "command",
    [
        'powershell -Command "Remove-Item important.txt"',
        "powershell -EncodedCommand SGVsbG8=",
    ],
)
def test_dangerous_commands_never_return_safe_result(
    policy: SecurityPolicy,
    command: str,
) -> None:
    """Known dangerous commands must always produce a risk result."""
    result = policy.inspect_command(command)

    assert result is not None
    assert result[0] == RiskLevel.CRITICAL


def test_command_inspection_is_repeatable(policy: SecurityPolicy) -> None:
    """Repeated inspection should return consistent results."""
    command = 'powershell -Command "Remove-Item important.txt"'

    first_result = policy.inspect_command(command)
    second_result = policy.inspect_command(command)

    assert first_result == second_result


def test_safe_command_does_not_mutate_policy(policy: SecurityPolicy) -> None:
    """Inspecting a safe command should not change policy configuration."""
    original_config = policy.config

    policy.inspect_command("echo hello")

    assert policy.config == original_config
