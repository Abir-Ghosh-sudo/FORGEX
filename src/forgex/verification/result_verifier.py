"""Execution result verification for FORGEX.

Verifies terminal execution results, test outcomes, and agent outputs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExecutionVerificationResult:
    """Result of execution verification."""

    verified: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ResultVerifier:
    """Verifies execution results from tools and agents."""

    def verify_terminal_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        expected_success: bool = True,
    ) -> ExecutionVerificationResult:
        """Verify a terminal command result."""
        result = ExecutionVerificationResult(verified=True)

        if expected_success and exit_code != 0:
            result.verified = False
            result.errors.append(f"Command failed with exit code {exit_code}")
            if stderr:
                result.errors.append(f"Stderr: {stderr[:500]}")

        result.checks.append(
            {
                "name": "exit_code",
                "passed": exit_code == 0 or not expected_success,
                "detail": str(exit_code),
            }
        )
        result.checks.append(
            {
                "name": "stdout_present",
                "passed": bool(stdout.strip()),
                "detail": f"{len(stdout)} chars",
            }
        )
        if stderr:
            result.warnings.append(f"Stderr produced ({len(stderr)} chars)")

        return result

    def verify_test_result(
        self,
        total: int,
        passed: int,
        failed: int,
        errors: int,
    ) -> ExecutionVerificationResult:
        """Verify test execution results."""
        result = ExecutionVerificationResult(verified=(failed == 0 and errors == 0))

        result.checks.append(
            {"name": "total_tests", "passed": total > 0, "detail": str(total)}
        )
        result.checks.append(
            {
                "name": "all_passed",
                "passed": failed == 0 and errors == 0,
                "detail": f"passed={passed}, failed={failed}, errors={errors}",
            }
        )

        if failed > 0:
            result.errors.append(f"{failed} test(s) failed.")
        if errors > 0:
            result.errors.append(f"{errors} test(s) errored.")

        return result

    def verify_agent_output(
        self,
        output: Any,
        required_keys: list[str] | None = None,
    ) -> ExecutionVerificationResult:
        """Verify agent output structure."""
        result = ExecutionVerificationResult(verified=True)

        if output is None:
            result.verified = False
            result.errors.append("Agent output is None.")
            return result

        if isinstance(output, dict):
            for key in required_keys or []:
                if key not in output:
                    result.verified = False
                    result.errors.append(f"Missing required key: {key}")
        elif isinstance(output, str) and not output.strip():
            result.verified = False
            result.errors.append("Agent output is empty string.")

        return result


__all__ = ["ResultVerifier", "ExecutionVerificationResult"]
