"""Tester workflow node."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from forgex.agents.nodes.base import AgentNode
from forgex.agents.roles.tester import TesterRole
from forgex.core.orchestrator import ForgexState


class TesterNode(AgentNode):
    """Evaluates verification status and executes real project tests."""

    node_name = "tester"
    state_key = "test_report"

    def __init__(self, role: TesterRole | None = None, model: Any = None) -> None:
        super().__init__(role or TesterRole(model=model))

    async def __call__(self, state: ForgexState) -> dict[str, Any]:
        update = await super().__call__(state)
        report = dict(update.get("test_report") or {})

        raw_workspace = state.get("workspace") or Path.cwd()
        workspace = Path(raw_workspace).expanduser().resolve()

        # Check if actual test files exist in the target workspace
        has_tests = False
        if workspace.is_dir():
            has_tests = (
                (workspace / "tests").is_dir()
                or any(workspace.glob("test_*.py"))
                or any(workspace.glob("*_test.py"))
            )

        # Run real test suite if workspace contains test files
        if has_tests:
            try:
                process = await asyncio.create_subprocess_exec(
                    "pytest",
                    "-q",
                    cwd=str(workspace),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=60.0,
                )
                stdout = stdout_bytes.decode(errors="replace")
                stderr = stderr_bytes.decode(errors="replace")
                exit_code = process.returncode or 0

                if exit_code == 0:
                    report["verified"] = True
                    report["summary"] = report.get("summary") or "All workspace tests passed."
                    report["next_action"] = "complete"
                    report["failures"] = []
                    report["test_output"] = stdout
                else:
                    report["verified"] = False
                    report["summary"] = f"Tests failed (exit code {exit_code})"
                    report["next_action"] = "fix"
                    report["failures"] = [stderr or stdout]
                    report["test_output"] = stdout + "\n" + stderr
            except asyncio.TimeoutError:
                report["verified"] = False
                report["next_action"] = "fix"
                report["failures"] = ["Test execution timed out after 60 seconds."]
                report["test_output"] = ""
            except Exception as exc:
                report["verified"] = False  # Fail closed — never trust model on runner error
                report["next_action"] = "fix"
                report["failures"] = [f"Test runner error: {exc!s}"]
                report["test_output"] = ""

        # If workspace has no tests, never accept model's verified=True
        if not has_tests:
            report["verified"] = False
            if not report.get("failures"):
                report["failures"] = ["No test files found in workspace; cannot verify implementation."]
            if not report.get("next_action"):
                report["next_action"] = "fix"

        update["test_report"] = report
        update["output"] = report
        metadata = dict(update.get("metadata") or {})
        cycles = int(metadata.get("test_cycles", 0))
        metadata["test_cycles"] = cycles + 1
        update["metadata"] = metadata
        failures = report.get("failures") or []
        if failures and not report.get("verified", False):
            update["error"] = "; ".join(str(item) for item in failures)
        elif report.get("verified", False):
            update["error"] = ""
        return update


__all__ = ["TesterNode"]
