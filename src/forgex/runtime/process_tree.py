
"""Cross-platform subprocess tree management for FORGEX."""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger(__name__)


class TerminationStatus(StrEnum):
    TERMINATED = "terminated"
    ALREADY_EXITED = "already_exited"
    FORCE_KILLED = "force_killed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TerminationResult:
    pid: int
    status: TerminationStatus
    elapsed_seconds: float
    error: str | None = None


class ProcessTreeManager:
    """Terminate subprocess trees using native operating-system APIs.

    POSIX processes should be launched with start_new_session=True.
    Windows processes should be launched with CREATE_NEW_PROCESS_GROUP.

    This manager never launches processes itself.
    """

    def __init__(self, grace_period: float = 3.0) -> None:
        if grace_period < 0:
            raise ValueError("grace_period cannot be negative.")

        self.grace_period = grace_period

    def terminate(
        self,
        pid: int,
        *,
        force: bool = False,
    ) -> TerminationResult:
        """Terminate a process and its process group."""

        if pid <= 0:
            raise ValueError("PID must be a positive integer.")

        started = time.monotonic()

        if not self._is_alive(pid):
            return TerminationResult(
                pid=pid,
                status=TerminationStatus.ALREADY_EXITED,
                elapsed_seconds=time.monotonic() - started,
            )

        try:
            self._send_termination(pid, force=force)

            if force:
                return TerminationResult(
                    pid=pid,
                    status=TerminationStatus.FORCE_KILLED,
                    elapsed_seconds=time.monotonic() - started,
                )

            if self._wait(pid, self.grace_period):
                return TerminationResult(
                    pid=pid,
                    status=TerminationStatus.TERMINATED,
                    elapsed_seconds=time.monotonic() - started,
                )

            self._send_termination(pid, force=True)

            return TerminationResult(
                pid=pid,
                status=TerminationStatus.FORCE_KILLED,
                elapsed_seconds=time.monotonic() - started,
            )

        except (OSError, PermissionError, ProcessLookupError) as exc:
            logger.exception("Failed to terminate process tree %s.", pid)

            return TerminationResult(
                pid=pid,
                status=TerminationStatus.FAILED,
                elapsed_seconds=time.monotonic() - started,
                error=str(exc),
            )

    def _send_termination(self, pid: int, *, force: bool) -> None:
        if os.name == "nt":
            self._terminate_windows(pid, force=force)
        else:
            self._terminate_posix(pid, force=force)

    @staticmethod
    def _terminate_posix(pid: int, *, force: bool) -> None:
        """Signal the complete POSIX process group."""

        sig = signal.SIGKILL if force else signal.SIGTERM

        try:
            os.killpg(pid, sig)
        except ProcessLookupError:
            # The process may have exited between the liveness check
            # and signal delivery. Fall back to checking the PID.
            if ProcessTreeManager._is_alive(pid):
                os.kill(pid, sig)

    @staticmethod
    def _terminate_windows(pid: int, *, force: bool) -> None:
        """Terminate descendants using Windows taskkill."""

        command = ["taskkill", "/PID", str(pid), "/T"]

        if force:
            command.append("/F")

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if completed.returncode != 0:
            if not ProcessTreeManager._is_alive(pid):
                return

            raise OSError(
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"taskkill failed with exit code {completed.returncode}"
            )

    @staticmethod
    def _is_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def _wait(pid: int, timeout: float) -> bool:
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            if not ProcessTreeManager._is_alive(pid):
                return True

            time.sleep(0.05)

        return not ProcessTreeManager._is_alive(pid)
