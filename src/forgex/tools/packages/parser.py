"""Package manager output parsers."""

from __future__ import annotations

import json
import re
from typing import Any

from forgex.tools.packages.models import (
    InstalledPackage,
    PackageManager,
)


class PackageParseError(ValueError):
    """Raised when package output cannot be parsed."""


class PackageOutputParser:
    """Parse installed package information."""

    def parse(
        self,
        output: str,
        manager: PackageManager,
    ) -> tuple[InstalledPackage, ...]:
        if not output.strip():
            return ()

        parsers = {
            PackageManager.PIP: self.parse_pip,
            PackageManager.UV: self.parse_pip,
            PackageManager.NPM: self.parse_npm,
            PackageManager.PNPM: self.parse_npm,
            PackageManager.YARN: self.parse_yarn,
            PackageManager.BUN: self.parse_npm,
            PackageManager.CARGO: self.parse_cargo,
            PackageManager.GO: self.parse_go,
        }

        parser = parsers.get(manager)

        if parser is None:
            raise PackageParseError(f"Parsing is not supported for {manager.value}")

        try:
            return parser(output, manager)
        except (ValueError, TypeError, KeyError) as exc:
            raise PackageParseError(f"Unable to parse {manager.value} output: {exc}") from exc

    def parse_pip(
        self,
        output: str,
        manager: PackageManager = PackageManager.PIP,
    ) -> tuple[InstalledPackage, ...]:
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return self._parse_pip_text(output, manager)

        packages = data.get("packages", data) if isinstance(data, dict) else data

        if not isinstance(packages, list):
            raise PackageParseError("Expected a package list")

        return tuple(
            InstalledPackage(
                name=item["name"],
                version=str(item["version"]),
                manager=manager,
                description=item.get("summary"),
                location=item.get("location"),
            )
            for item in packages
            if isinstance(item, dict) and item.get("name")
        )

    def _parse_pip_text(
        self,
        output: str,
        manager: PackageManager,
    ) -> tuple[InstalledPackage, ...]:
        results = []

        for line in output.splitlines():
            match = re.match(
                r"^([A-Za-z0-9_.-]+)\s+([^\s]+)",
                line.strip(),
            )

            if not match:
                continue

            name, version = match.groups()

            if name.lower() in ("package", "---"):
                continue

            results.append(
                InstalledPackage(
                    name=name,
                    version=version,
                    manager=manager,
                )
            )

        return tuple(results)

    def parse_npm(
        self,
        output: str,
        manager: PackageManager = PackageManager.NPM,
    ) -> tuple[InstalledPackage, ...]:
        data = json.loads(output)

        entries = data if isinstance(data, list) else data.get("dependencies", [])

        results = []

        for item in entries:
            if not isinstance(item, dict):
                continue

            name = item.get("name")
            version = item.get("version")

            if not name:
                continue

            if version is None:
                version = item.get("current")

            if version is None:
                continue

            results.append(
                InstalledPackage(
                    name=name,
                    version=str(version),
                    manager=manager,
                    description=item.get("description"),
                    dependencies=tuple(item.get("dependencies", {}).keys())
                    if isinstance(item.get("dependencies"), dict)
                    else (),
                )
            )

        return tuple(results)

    def parse_yarn(
        self,
        output: str,
        manager: PackageManager = PackageManager.YARN,
    ) -> tuple[InstalledPackage, ...]:
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return self._parse_yarn_text(output, manager)

        results = []

        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue

            name = item.get("name")
            version = item.get("value") or item.get("version")

            if name and version:
                results.append(
                    InstalledPackage(
                        name=name,
                        version=str(version),
                        manager=manager,
                    )
                )

        return tuple(results)

    def _parse_yarn_text(
        self,
        output: str,
        manager: PackageManager,
    ) -> tuple[InstalledPackage, ...]:
        results = []

        for line in output.splitlines():
            match = re.match(
                r"^\s*[├└]──\s+(.+?)@([^\s]+)",
                line,
            )

            if match:
                results.append(
                    InstalledPackage(
                        name=match.group(1),
                        version=match.group(2),
                        manager=manager,
                    )
                )

        return tuple(results)

    def parse_cargo(
        self,
        output: str,
        manager: PackageManager = PackageManager.CARGO,
    ) -> tuple[InstalledPackage, ...]:
        results = []

        for line in output.splitlines():
            match = re.match(
                r"^\s*([A-Za-z0-9_-]+)\s+v?([0-9][^\s]*)",
                line,
            )

            if not match:
                continue

            name, version = match.groups()

            if name == "├" or name == "└":
                continue

            results.append(
                InstalledPackage(
                    name=name,
                    version=version,
                    manager=manager,
                )
            )

        return tuple(results)

    def parse_go(
        self,
        output: str,
        manager: PackageManager = PackageManager.GO,
    ) -> tuple[InstalledPackage, ...]:
        results = []

        for line in output.splitlines():
            parts = line.split()

            if len(parts) < 2:
                continue

            name, version = parts[:2]

            if name == "Path":
                continue

            results.append(
                InstalledPackage(
                    name=name,
                    version=version,
                    manager=manager,
                )
            )

        return tuple(results)

    @staticmethod
    def parse_json(output: str) -> Any:
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise PackageParseError(f"Invalid JSON output: {exc}") from exc
