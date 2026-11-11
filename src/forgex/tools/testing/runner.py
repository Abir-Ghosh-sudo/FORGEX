"""Test execution runner for FORGEX."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from forgex.runtime.supervisor import (
    ProcessSupervisor,
    SupervisedProcessState,
)
from forgex.tools.testing.frameworks import (
    FrameworkDetectionError,
    TestCommandResolver,
)
from forgex.tools.testing.models import (
    TestFramework,
    TestRequest,
    TestRunResult,
    TestStatus,
)


class TestRunnerError(RuntimeError):
    """Raised when test execution cannot be completed."""


class TestRunner:
    """Execute project tests through the runtime supervisor."""

    def __init__(
        self,
        supervisor: ProcessSupervisor,
        resolver: TestCommandResolver | None = None,
    ) -> None:
        self.supervisor = supervisor
        self.resolver = resolver or TestCommandResolver()

    async def run(self, request: TestRequest) -> TestRunResult:
        workspace = Path(request.workspace).expanduser().resolve()

        if not workspace.is_dir():
            raise TestRunnerError(
                f"Workspace does not exist: {workspace}"
            )

        started_at = datetime.now(timezone.utc)
        start_time = time.monotonic()
        run_id = uuid.uuid4().hex

        framework = request.framework
        command: tuple[str, ...] = ()

        try:
            if framework == TestFramework.AUTO:
                detected = self.resolver.detector.detect(workspace)
                framework = detected.framework

            resolved_request = TestRequest(
                workspace=workspace,
                framework=framework,
                target=request.target,
                test_paths=request.test_paths,
                markers=request.markers,
                extra_args=request.extra_args,
                environment=request.environment,
                timeout_seconds=request.timeout_seconds,
                max_output_bytes=request.max_output_bytes,
                coverage=request.coverage,
                fail_fast=request.fail_fast,
                parallel=request.parallel,
                session_id=request.session_id,
            )

            command = self.resolver.resolve(resolved_request)

            if not self.resolver.is_available(command):
                raise TestRunnerError(
                    f"Test executable not available: {command[0]}"
                )

            environment = os.environ.copy()
            environment.update(request.environment)

            supervised = await self.supervisor.execute(
                list(command),
                cwd=workspace,
                env=environment,
                timeout=request.timeout_seconds,
            )

            output = supervised.output
            stdout = self._decode(output.stdout)
            stderr = self._decode(output.stderr)

            status = self._map_status(
                supervised.state,
                supervised.return_code,
            )

            finished_at = datetime.now(timezone.utc)

            return TestRunResult(
                run_id=run_id,
                framework=framework,
                status=status,
                workspace=workspace,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=time.monotonic() - start_time,
                exit_code=supervised.return_code,
                stdout=stdout[: request.max_output_bytes],
                stderr=stderr[: request.max_output_bytes],
                output_truncated=(
                    len(stdout.encode("utf-8", errors="replace"))
                    + len(stderr.encode("utf-8", errors="replace"))
                    > request.max_output_bytes
                ),
                command=command,
            )

        except asyncio.CancelledError:
            raise

        except (FrameworkDetectionError, TestRunnerError):
            raise

        except Exception as exc:
            raise TestRunnerError(
                f"Test execution failed: {exc}"
            ) from exc

    @staticmethod
    def _decode(value: bytes | str | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)

    @staticmethod
    def _map_status(
        state: SupervisedProcessState,
        return_code: int,
    ) -> TestStatus:
        if state == SupervisedProcessState.COMPLETED:
            return (
                TestStatus.PASSED
                if return_code == 0
                else TestStatus.FAILED
            )

        if state == SupervisedProcessState.TIMED_OUT:
            return TestStatus.TIMEOUT

        if state == SupervisedProcessState.CANCELLED:
            return TestStatus.CANCELLED

        return TestStatus.ERROR