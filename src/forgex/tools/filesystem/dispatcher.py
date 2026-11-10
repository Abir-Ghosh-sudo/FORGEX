
"""Validated operation dispatcher for FORGEX filesystem tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from forgex.tools.filesystem.toolkit import (
    FilesystemToolkit,
    FilesystemToolResult,
)


class FilesystemDispatchError(Exception):
    """Raised when a filesystem operation cannot be dispatched."""


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Description of a supported filesystem operation."""

    name: str
    handler: Callable[..., FilesystemToolResult]
    required_arguments: frozenset[str]
    optional_arguments: frozenset[str]


class FilesystemDispatcher:
    """Dispatch validated operation requests to FilesystemToolkit."""

    def __init__(self, toolkit: FilesystemToolkit) -> None:
        if not isinstance(toolkit, FilesystemToolkit):
            raise TypeError("toolkit must be FilesystemToolkit.")

        self._toolkit = toolkit
        self._operations = self._build_registry()

    def _build_registry(self) -> dict[str, OperationSpec]:
        handlers = {
            "read_file": (
                self._toolkit.read_file,
                {"path"},
                {"start_line", "end_line"},
            ),
            "write_file": (
                self._toolkit.write_file,
                {"path", "content"},
                {"overwrite"},
            ),
            "delete_file": (
                self._toolkit.delete_file,
                {"path"},
                {"permanent", "confirm"},
            ),
            "copy_path": (
                self._toolkit.copy_path,
                {"source", "destination"},
                {"overwrite"},
            ),
            "move_path": (
                self._toolkit.move_path,
                {"source", "destination"},
                {"overwrite"},
            ),
            "rename_path": (
                self._toolkit.rename_path,
                {"source", "new_name"},
                {"overwrite"},
            ),
            "search_files": (
                self._toolkit.search_files,
                {"pattern"},
                {"recursive"},
            ),
            "search_content": (
                self._toolkit.search_content,
                {"query"},
                {
                    "file_pattern",
                    "case_sensitive",
                    "use_regex",
                },
            ),
            "inspect_directory": (
                self._toolkit.inspect_directory,
                set(),
                {"path", "recursive", "max_depth"},
            ),
            "inspect_metadata": (
                self._toolkit.inspect_metadata,
                {"path"},
                set(),
            ),
            "get_tree": (
                self._toolkit.get_tree,
                set(),
                {"path", "max_depth"},
            ),
        }

        return {
            name: OperationSpec(
                name=name,
                handler=handler,
                required_arguments=frozenset(required),
                optional_arguments=frozenset(optional),
            )
            for name, (
                handler,
                required,
                optional,
            ) in handlers.items()
        }

    @property
    def available_operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    def describe_operations(self) -> list[dict[str, Any]]:
        """Return operation descriptions suitable for agent prompts."""

        return [
            {
                "name": spec.name,
                "required_arguments": sorted(
                    spec.required_arguments
                ),
                "optional_arguments": sorted(
                    spec.optional_arguments
                ),
            }
            for spec in sorted(
                self._operations.values(),
                key=lambda item: item.name,
            )
        ]

    def dispatch(
        self,
        operation: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> FilesystemToolResult:
        """Validate and execute one filesystem operation."""

        if not isinstance(operation, str) or not operation.strip():
            raise FilesystemDispatchError(
                "Operation name must be a non-empty string."
            )

        spec = self._operations.get(operation)

        if spec is None:
            raise FilesystemDispatchError(
                f"Unsupported filesystem operation: {operation}"
            )

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, Mapping):
            raise FilesystemDispatchError(
                "Operation arguments must be a mapping."
            )

        supplied = set(arguments)
        allowed = spec.required_arguments | spec.optional_arguments

        missing = spec.required_arguments - supplied
        unknown = supplied - allowed

        if missing:
            raise FilesystemDispatchError(
                f"Missing required arguments: {sorted(missing)}"
            )

        if unknown:
            raise FilesystemDispatchError(
                f"Unsupported arguments: {sorted(unknown)}"
            )

        try:
            return spec.handler(**dict(arguments))
        except Exception as exc:
            raise FilesystemDispatchError(
                f"Could not dispatch '{operation}': {exc}"
            ) from exc
