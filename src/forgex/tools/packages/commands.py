"""Safe package manager command construction."""

from __future__ import annotations

import re

from forgex.tools.packages.models import (
    PackageManager,
    PackageOperation,
    PackageRequest,
    PackageSpec,
)


class PackageCommandError(ValueError):
    """Raised when a package command cannot be safely constructed."""


class PackageCommandBuilder:
    """Build argument arrays for supported package managers."""

    _PACKAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    _VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]*$")

    def build(
        self,
        request: PackageRequest,
        manager: PackageManager | None = None,
    ) -> tuple[str, ...]:
        selected = manager or request.manager

        if selected == PackageManager.AUTO:
            raise PackageCommandError("A concrete package manager must be selected.")

        packages = tuple(self._format_package(package, selected) for package in request.packages)

        builders = {
            PackageManager.PIP: self._pip,
            PackageManager.UV: self._uv,
            PackageManager.POETRY: self._poetry,
            PackageManager.NPM: self._npm,
            PackageManager.PNPM: self._pnpm,
            PackageManager.YARN: self._yarn,
            PackageManager.BUN: self._bun,
            PackageManager.CARGO: self._cargo,
            PackageManager.GO: self._go,
            PackageManager.DOTNET: self._dotnet,
        }

        builder = builders.get(selected)

        if builder is None:
            raise PackageCommandError(f"Unsupported package manager: {selected}")

        command = builder(request, packages)

        if request.dry_run and request.operation in (
            PackageOperation.INSTALL,
            PackageOperation.UNINSTALL,
            PackageOperation.UPDATE,
        ):
            if selected == PackageManager.PIP:
                return (*command, "--dry-run")
            if selected == PackageManager.UV:
                return (*command, "--dry-run")
            if selected in (
                PackageManager.NPM,
                PackageManager.PNPM,
            ):
                return (*command, "--dry-run")

            raise PackageCommandError(
                f"Dry-run is not supported for {selected.value} by this command builder."
            )

        return command

    def _format_package(
        self,
        package: PackageSpec,
        manager: PackageManager,
    ) -> str:
        name = package.name.strip()

        if not self._PACKAGE_NAME.fullmatch(name):
            raise PackageCommandError(f"Invalid package name: {name!r}")

        if package.version is not None:
            version = package.version.strip()

            if not self._VERSION.fullmatch(version):
                raise PackageCommandError(f"Invalid package version: {version!r}")
        else:
            version = None

        if package.source is not None:
            source = package.source.strip()

            if source.startswith("-") or "\x00" in source:
                raise PackageCommandError("Invalid package source")

            if manager in (
                PackageManager.NPM,
                PackageManager.PNPM,
                PackageManager.YARN,
                PackageManager.BUN,
                PackageManager.CARGO,
                PackageManager.GO,
                PackageManager.DOTNET,
            ):
                raise PackageCommandError(
                    f"Custom package sources are not supported for {manager.value}."
                )

            return source

        if manager in (PackageManager.NPM, PackageManager.PNPM):
            return f"{name}@{version}" if version else name

        if manager == PackageManager.YARN:
            return f"{name}@{version}" if version else name

        if manager == PackageManager.BUN:
            return f"{name}@{version}" if version else name

        if manager == PackageManager.CARGO:
            return f"{name}@{version}" if version else name

        if manager == PackageManager.GO:
            return f"{name}@v{version}" if version else name

        if manager == PackageManager.DOTNET:
            return f"{name} --version {version}" if version else name

        extras = f"[{','.join(package.extras)}]" if package.extras else ""
        return f"{name}{extras}=={version}" if version else f"{name}{extras}"

    def _pip(self, request, packages):
        base = ["python", "-m", "pip"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "install", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "uninstall", "-y", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "install", "--upgrade", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "list", "--format=json")
        if request.operation == PackageOperation.FREEZE:
            return (*base, "freeze")
        if request.operation == PackageOperation.CHECK:
            return (*base, "check")
        if request.operation == PackageOperation.AUDIT:
            return ("pip-audit",)
        if request.operation == PackageOperation.INFO:
            return (*base, "show", *packages)

        raise PackageCommandError("Unsupported pip operation")

    def _uv(self, request, packages):
        base = ["uv"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "pip", "install", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "pip", "uninstall", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "pip", "install", "--upgrade", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "pip", "list", "--format=json")
        if request.operation == PackageOperation.FREEZE:
            return (*base, "pip", "freeze")
        if request.operation == PackageOperation.CHECK:
            return (*base, "pip", "check")
        if request.operation == PackageOperation.INFO:
            return (*base, "pip", "show", *packages)

        raise PackageCommandError("Unsupported uv operation")

    def _poetry(self, request, packages):
        base = ["poetry"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "add", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "remove", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "update", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "show", "--format=json")
        if request.operation == PackageOperation.CHECK:
            return (*base, "check")
        if request.operation == PackageOperation.INFO:
            return (*base, "show", *packages)

        raise PackageCommandError("Unsupported poetry operation")

    def _npm(self, request, packages):
        base = ["npm"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "install", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "uninstall", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "update", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "list", "--json")
        if request.operation == PackageOperation.AUDIT:
            return (*base, "audit", "--json")
        if request.operation == PackageOperation.INFO:
            return (*base, "view", *packages)

        raise PackageCommandError("Unsupported npm operation")

    def _pnpm(self, request, packages):
        base = ["pnpm"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "add", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "remove", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "update", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "list", "--json")
        if request.operation == PackageOperation.AUDIT:
            return (*base, "audit", "--json")
        if request.operation == PackageOperation.INFO:
            return (*base, "view", *packages)

        raise PackageCommandError("Unsupported pnpm operation")

    def _yarn(self, request, packages):
        base = ["yarn"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "add", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "remove", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "up", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "list", "--json")
        if request.operation == PackageOperation.INFO:
            return (*base, "info", *packages)

        raise PackageCommandError("Unsupported yarn operation")

    def _bun(self, request, packages):
        base = ["bun"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "add", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "remove", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "update", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "pm", "ls")
        if request.operation == PackageOperation.INFO:
            return (*base, "pm", "view", *packages)

        raise PackageCommandError("Unsupported bun operation")

    def _cargo(self, request, packages):
        base = ["cargo"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "add", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "remove", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "update", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "tree", "--depth", "1")
        if request.operation == PackageOperation.CHECK:
            return (*base, "check")
        if request.operation == PackageOperation.INFO:
            return ("cargo", "search", *packages)

        raise PackageCommandError("Unsupported cargo operation")

    def _go(self, request, packages):
        base = ["go"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "get", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            raise PackageCommandError("Go modules do not support direct package uninstall.")
        if request.operation == PackageOperation.UPDATE:
            return (*base, "get", *(f"{p}@latest" for p in packages))
        if request.operation == PackageOperation.LIST:
            return (*base, "list", "-m", "all")
        if request.operation == PackageOperation.INFO:
            return (*base, "list", "-m", "-json", *packages)

        raise PackageCommandError("Unsupported go operation")

    def _dotnet(self, request, packages):
        base = ["dotnet"]

        if request.operation == PackageOperation.INSTALL:
            return (*base, "add", "package", *packages)
        if request.operation == PackageOperation.UNINSTALL:
            return (*base, "remove", "package", *packages)
        if request.operation == PackageOperation.UPDATE:
            return (*base, "add", "package", *packages)
        if request.operation == PackageOperation.LIST:
            return (*base, "list", "package")
        if request.operation == PackageOperation.INFO:
            return (*base, "package", "search", *packages)

        raise PackageCommandError("Unsupported dotnet operation")
