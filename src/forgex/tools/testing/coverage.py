"""Coverage report collection and analysis."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from forgex.tools.testing.models import CoverageSummary


class CoverageError(RuntimeError):
    """Raised when coverage analysis fails."""


class CoverageAnalyzer:
    """Analyze Python coverage reports."""

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).expanduser().resolve()

        if not self.workspace.is_dir():
            raise CoverageError(
                f"Workspace does not exist: {self.workspace}"
            )

    def collect(self) -> CoverageSummary:
        """Collect coverage from the default coverage database."""

        executable = shutil.which("coverage")

        if executable is None:
            raise CoverageError(
                "coverage.py is not installed. Install it with "
                "'pip install coverage'."
            )

        report = self.workspace / ".coverage"
        if not report.exists():
            raise CoverageError(
                "Coverage data not found. Run tests with coverage enabled."
            )

        output_path = self.workspace / ".forgex-coverage.json"

        command = [
            executable,
            "json",
            "-o",
            str(output_path),
        ]

        try:
            result = subprocess.run(
                command,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CoverageError(
                f"Coverage report generation failed: {exc}"
            ) from exc

        if result.returncode != 0:
            raise CoverageError(
                result.stderr.strip()
                or "Unable to generate coverage JSON."
            )

        try:
            data = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CoverageError(
                f"Invalid coverage JSON: {exc}"
            ) from exc
        finally:
            output_path.unlink(missing_ok=True)

        totals = data.get("totals", {})

        return CoverageSummary(
            line_percent=self._percentage(
                totals.get("percent_covered")
            ),
            branch_percent=self._percentage(
                totals.get("percent_branches_covered")
            ),
            statements=int(totals.get("num_statements", 0)),
            statements_covered=int(
                totals.get("covered_lines", 0)
            ),
            branches=int(totals.get("num_branches", 0)),
            branches_covered=int(
                totals.get("covered_branches", 0)
            ),
            report_path=report,
        )

    def analyze_file(self, file_path: str) -> dict[str, Any]:
        """Return coverage details for a single source file."""

        target = (self.workspace / file_path).resolve()

        if not target.is_relative_to(self.workspace):
            raise CoverageError("File is outside the workspace.")

        if not target.is_file():
            raise CoverageError(f"File not found: {file_path}")

        executable = shutil.which("coverage")
        if executable is None:
            raise CoverageError("coverage.py is not installed.")

        output_path = self.workspace / ".forgex-coverage.json"

        try:
            result = subprocess.run(
                [
                    executable,
                    "json",
                    "-o",
                    str(output_path),
                    str(target),
                ],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            if result.returncode != 0:
                raise CoverageError(
                    result.stderr.strip()
                    or "Coverage analysis failed."
                )

            data = json.loads(
                output_path.read_text(encoding="utf-8")
            )

            relative = target.relative_to(self.workspace).as_posix()
            files = data.get("files", {})
            file_data = files.get(relative)

            if file_data is None:
                file_data = next(
                    (
                        value
                        for name, value in files.items()
                        if Path(name).name == target.name
                    ),
                    None,
                )

            if file_data is None:
                raise CoverageError(
                    f"No coverage data found for {relative}"
                )

            summary = file_data.get("summary", {})

            return {
                "file": relative,
                "percent_covered": self._percentage(
                    summary.get("percent_covered")
                ),
                "statements": summary.get("num_statements", 0),
                "covered_lines": summary.get("covered_lines", 0),
                "missing_lines": file_data.get("missing_lines", []),
                "excluded_lines": file_data.get("excluded_lines", []),
                "executed_lines": file_data.get("executed_lines", []),
                "missing_branches": file_data.get(
                    "missing_branches", []
                ),
            }

        except (OSError, json.JSONDecodeError) as exc:
            raise CoverageError(
                f"Unable to analyze coverage: {exc}"
            ) from exc

        finally:
            output_path.unlink(missing_ok=True)

    @staticmethod
    def _percentage(value: Any) -> float | None:
        if value is None:
            return None

        try:
            percentage = float(value)
        except (TypeError, ValueError):
            return None

        return max(0.0, min(100.0, percentage))