"""Test output parsers for FORGEX."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from forgex.tools.testing.models import (
    TestCaseResult,
    TestStatus,
)


class TestOutputParser:
    """Parse test execution output into structured test results."""

    PYTEST_PATTERN = re.compile(
        r"^(.*?)\s+(PASSED|FAILED|SKIPPED|ERROR)(?:\s+\[.*?\])?"
        r"(?:\s+-\s+(.*))?$",
        re.IGNORECASE | re.MULTILINE,
    )

    PYTEST_LOCATION = re.compile(
        r"^(.+?):(\d+):\s*(.*)$"
    )

    UNITTEST_PATTERN = re.compile(
        r"^(test_\w+)\s+\(([^)]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR|skipped.*)$",
        re.MULTILINE | re.IGNORECASE,
    )

    def parse_pytest(self, output: str) -> tuple[TestCaseResult, ...]:
        results: list[TestCaseResult] = []

        for match in self.PYTEST_PATTERN.finditer(output):
            name, raw_status, message = match.groups()

            location = self.PYTEST_LOCATION.match(name.strip())
            file_path = None
            line_number = None
            test_name = name.strip()

            if location:
                file_path = location.group(1)
                line_number = int(location.group(2))
                test_name = location.group(3).strip()

            results.append(
                TestCaseResult(
                    name=test_name,
                    status=self._status(raw_status),
                    file_path=file_path,
                    line_number=line_number,
                    message=message.strip() if message else None,
                )
            )

        return tuple(results)

    def parse_unittest(self, output: str) -> tuple[TestCaseResult, ...]:
        results: list[TestCaseResult] = []

        for match in self.UNITTEST_PATTERN.finditer(output):
            name, module, raw_status = match.groups()

            status_text = raw_status.lower()

            if status_text.startswith("ok"):
                status = TestStatus.PASSED
            elif status_text.startswith("skipped"):
                status = TestStatus.SKIPPED
            elif status_text == "fail":
                status = TestStatus.FAILED
            else:
                status = TestStatus.ERROR

            results.append(
                TestCaseResult(
                    name=f"{module}.{name}",
                    status=status,
                    message=(
                        raw_status
                        if status != TestStatus.PASSED
                        else None
                    ),
                )
            )

        return tuple(results)

    def parse_junit_xml(
        self,
        xml_path: Path,
    ) -> tuple[TestCaseResult, ...]:
        """Parse JUnit-compatible XML reports."""

        import xml.etree.ElementTree as ET

        path = Path(xml_path)

        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as exc:
            raise ValueError(
                f"Unable to parse JUnit XML: {exc}"
            ) from exc

        results: list[TestCaseResult] = []

        for case in root.iter("testcase"):
            name = case.attrib.get("name", "unknown")
            classname = case.attrib.get("classname", "")
            file_path = case.attrib.get("file")
            duration = self._float(
                case.attrib.get("time", "0")
            )

            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")

            if failure is not None:
                status = TestStatus.FAILED
                message = failure.attrib.get("message")
                traceback = failure.text
            elif error is not None:
                status = TestStatus.ERROR
                message = error.attrib.get("message")
                traceback = error.text
            elif skipped is not None:
                status = TestStatus.SKIPPED
                message = skipped.attrib.get("message")
                traceback = skipped.text
            else:
                status = TestStatus.PASSED
                message = None
                traceback = None

            results.append(
                TestCaseResult(
                    name=f"{classname}.{name}".strip("."),
                    status=status,
                    duration_seconds=duration,
                    file_path=file_path,
                    message=message,
                    traceback=traceback,
                )
            )

        return tuple(results)

    def parse_jest_json(
        self,
        report: str | dict[str, Any],
    ) -> tuple[TestCaseResult, ...]:
        """Parse Jest/Vitest JSON report data."""

        try:
            data = json.loads(report) if isinstance(report, str) else report
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid test JSON report") from exc

        results: list[TestCaseResult] = []

        for suite in data.get("testResults", []):
            file_path = suite.get("name")

            for assertion in suite.get("assertionResults", []):
                raw_status = assertion.get("status", "unknown")
                status_map = {
                    "passed": TestStatus.PASSED,
                    "failed": TestStatus.FAILED,
                    "pending": TestStatus.SKIPPED,
                    "skipped": TestStatus.SKIPPED,
                    "todo": TestStatus.SKIPPED,
                }

                status = status_map.get(
                    raw_status.lower(),
                    TestStatus.ERROR,
                )

                name_parts = assertion.get("fullName") or [
                    assertion.get("ancestorTitles", []),
                    [assertion.get("title", "unknown")],
                ]

                if isinstance(name_parts, str):
                    test_name = name_parts
                else:
                    flattened = []
                    for part in name_parts:
                        if isinstance(part, list):
                            flattened.extend(part)
                        else:
                            flattened.append(str(part))
                    test_name = " ".join(flattened)

                messages = assertion.get("failureMessages", [])

                results.append(
                    TestCaseResult(
                        name=test_name,
                        status=status,
                        file_path=file_path,
                        message=messages[0] if messages else None,
                        traceback="\n".join(messages) if messages else None,
                        duration_seconds=self._float(
                            assertion.get("duration", 0)
                        ) / 1000,
                    )
                )

        return tuple(results)

    def parse_summary(self, output: str) -> dict[str, int]:
        """Extract common test summary counters."""

        patterns = {
            "passed": r"(\d+)\s+passed",
            "failed": r"(\d+)\s+failed",
            "skipped": r"(\d+)\s+skipped",
            "errors": r"(\d+)\s+errors?",
        }

        summary: dict[str, int] = {}

        for key, pattern in patterns.items():
            matches = re.findall(pattern, output, re.IGNORECASE)
            summary[key] = int(matches[-1]) if matches else 0

        summary["total"] = sum(summary.values())
        return summary

    @staticmethod
    def _status(value: str) -> TestStatus:
        mapping = {
            "passed": TestStatus.PASSED,
            "failed": TestStatus.FAILED,
            "skipped": TestStatus.SKIPPED,
            "error": TestStatus.ERROR,
        }
        return mapping.get(value.lower(), TestStatus.ERROR)

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return 0.0