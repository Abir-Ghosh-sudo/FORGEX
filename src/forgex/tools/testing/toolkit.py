"""Unified testing toolkit for FORGEX."""

from __future__ import annotations

from pathlib import Path

from forgex.runtime.supervisor import ProcessSupervisor
from forgex.tools.testing.coverage import (
    CoverageAnalyzer,
    CoverageError,
)
from forgex.tools.testing.frameworks import (
    FrameworkDetectionError,
    FrameworkDetector,
    TestCommandResolver,
)
from forgex.tools.testing.models import (
    CoverageSummary,
    TestFramework,
    TestRequest,
    TestRunResult,
)
from forgex.tools.testing.parsers import TestOutputParser
from forgex.tools.testing.runner import (
    TestRunner,
    TestRunnerError,
)


class TestingToolkitError(RuntimeError):
    """Unified testing toolkit error."""


class TestingToolkit:
    """High-level API for project test operations."""

    def __init__(
        self,
        workspace: Path,
        supervisor: ProcessSupervisor,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()

        if not self.workspace.is_dir():
            raise TestingToolkitError(f"Workspace does not exist: {self.workspace}")

        self.detector = FrameworkDetector()
        self.resolver = TestCommandResolver(self.detector)
        self.parser = TestOutputParser()
        self.runner = TestRunner(supervisor, self.resolver)
        self.coverage = CoverageAnalyzer(self.workspace)

    def detect_framework(self):
        """Detect the project's test framework."""
        try:
            return self.detector.detect(self.workspace)
        except FrameworkDetectionError as exc:
            raise TestingToolkitError(str(exc)) from exc

    def build_request(
        self,
        *,
        framework: TestFramework = TestFramework.AUTO,
        test_paths: tuple[str, ...] = (),
        markers: tuple[str, ...] = (),
        extra_args: tuple[str, ...] = (),
        timeout_seconds: float = 600.0,
        coverage: bool = False,
        fail_fast: bool = False,
        environment: dict[str, str] | None = None,
    ) -> TestRequest:
        return TestRequest(
            workspace=self.workspace,
            framework=framework,
            test_paths=test_paths,
            markers=markers,
            extra_args=extra_args,
            timeout_seconds=timeout_seconds,
            coverage=coverage,
            fail_fast=fail_fast,
            environment=environment or {},
        )

    async def run_tests(
        self,
        request: TestRequest | None = None,
        **options,
    ) -> TestRunResult:
        """Run tests and return a structured execution result."""

        if request is None:
            request = self.build_request(**options)

        if request.workspace.resolve() != self.workspace:
            raise TestingToolkitError("Test request workspace does not match toolkit workspace.")

        try:
            result = await self.runner.run(request)

            if result.framework == TestFramework.PYTEST:
                cases = self.parser.parse_pytest(result.stdout + "\n" + result.stderr)
            elif result.framework == TestFramework.UNITTEST:
                cases = self.parser.parse_unittest(result.stdout + "\n" + result.stderr)
            else:
                cases = ()

            if cases:
                from dataclasses import replace

                result = replace(result, cases=cases)

            return result

        except (TestRunnerError, FrameworkDetectionError) as exc:
            raise TestingToolkitError(str(exc)) from exc

    def get_coverage(self) -> CoverageSummary:
        """Collect the latest coverage summary."""
        try:
            return self.coverage.collect()
        except CoverageError as exc:
            raise TestingToolkitError(str(exc)) from exc

    def get_file_coverage(self, file_path: str) -> dict:
        """Analyze coverage for one source file."""
        try:
            return self.coverage.analyze_file(file_path)
        except CoverageError as exc:
            raise TestingToolkitError(str(exc)) from exc

    def parse_test_output(
        self,
        output: str,
        framework: TestFramework,
    ):
        """Parse raw test output."""
        if framework == TestFramework.PYTEST:
            return self.parser.parse_pytest(output)

        if framework == TestFramework.UNITTEST:
            return self.parser.parse_unittest(output)

        if framework in (TestFramework.JEST, TestFramework.VITEST):
            return self.parser.parse_jest_json(output)

        return ()

    def get_summary(self, result: TestRunResult) -> dict[str, int | bool]:
        """Generate a concise test execution summary."""
        return {
            "total": result.total,
            "passed": result.passed,
            "failed": result.failed,
            "skipped": result.skipped,
            "errors": result.errors,
            "success": result.success,
            "duration_seconds": result.duration_seconds,
            "exit_code": result.exit_code,
        }
