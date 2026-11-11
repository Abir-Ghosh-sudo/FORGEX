"""Tester workflow node using FORGEX's supervised test runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.tester import TesterRole
from forgex.core.orchestrator import ForgexState
from forgex.runtime.supervisor import ProcessSupervisor
from forgex.tools.testing.models import TestFramework
from forgex.tools.testing.toolkit import TestingToolkit


class TesterNode(AgentNode):
    """Runs detected project tests and trusts only the real runner result."""

    node_name = "tester"
    state_key = "test_report"

    def __init__(self, role: TesterRole | None = None, model: Any = None) -> None:
        super().__init__(role or TesterRole(model=model))

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        report = dict(update.get("test_report") or {})
        workspace = Path(state.get("workspace") or Path.cwd()).expanduser().resolve()

        if not workspace.is_dir():
            report.update(
                verified=False,
                next_action="fix",
                summary="Test verification could not start: workspace is missing.",
                failures=[f"Workspace does not exist: {workspace}"],
                test_output="",
            )
        else:
            supervisor = ProcessSupervisor()
            try:
                toolkit = TestingToolkit(workspace, supervisor)
                try:
                    detected = toolkit.detect_framework()
                    request = toolkit.build_request(
                        framework=detected.framework,
                        timeout_seconds=60.0,
                    )
                    result = await toolkit.run_tests(request)
                    verified = bool(result.success)
                    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
                    failures = [] if verified else [
                        output.strip() or f"Test runner finished with status: {result.status.value}"
                    ]
                    report.update(
                        verified=verified,
                        next_action="complete" if verified else "fix",
                        summary=(
                            f"Tests passed ({result.passed} passed, {result.failed} failed)."
                            if verified
                            else f"Tests did not pass (status: {result.status.value})."
                        ),
                        failures=failures,
                        test_output=output,
                        test_framework=result.framework.value,
                        test_status=result.status.value,
                        test_exit_code=result.exit_code,
                        test_duration_seconds=result.duration_seconds,
                    )
                except Exception as exc:
                    report.update(
                        verified=False,
                        next_action="fix",
                        summary="Test verification failed; implementation is unverified.",
                        failures=[f"Test runner error: {exc!s}"],
                        test_output="",
                    )
            finally:
                await supervisor.shutdown()

        update["test_report"] = report
        update["output"] = report
        metadata = dict(update.get("metadata") or {})
        metadata["test_cycles"] = int(metadata.get("test_cycles", 0)) + 1
        update["metadata"] = metadata

        failures = report.get("failures") or []
        update["error"] = (
            "; ".join(str(item) for item in failures)
            if failures and not report.get("verified", False)
            else ""
        )
        return update


__all__ = ["TesterNode"]
