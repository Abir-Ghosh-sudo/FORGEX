"""Validated, fail-safe dispatcher for FORGEX filesystem tools."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from forgex.tools.filesystem.toolkit import (
    FilesystemToolkit,
    FilesystemToolResult,
)


class FilesystemDispatchError(Exception):
    """Raised when a filesystem operation cannot be dispatched."""


@dataclass(frozen=True, slots=True)
class OperationSpec:
    """Immutable description of a supported filesystem operation."""

    name: str
    handler: Callable[..., FilesystemToolResult]
    required_arguments: frozenset[str]
    optional_arguments: frozenset[str]
    description: str

    @property
    def allowed_arguments(self) -> frozenset[str]:
        return self.required_arguments | self.optional_arguments


class FilesystemDispatcher:
    """Validate and dispatch requests to the filesystem toolkit."""

    def __init__(self, toolkit: FilesystemToolkit) -> None:
        if not isinstance(toolkit, FilesystemToolkit):
            raise TypeError("toolkit must be FilesystemToolkit.")

        self._toolkit = toolkit
        self._operations = MappingProxyType(self._build_registry())

    def _build_registry(self) -> dict[str, OperationSpec]:
        definitions = {
            "read_file": (
                self._toolkit.read_file,
                {"path"},
                {"start_line", "end_line"},
                "Read a file or a selected line range.",
            ),
            "write_file": (
                self._toolkit.write_file,
                {"path", "content"},
                {"overwrite"},
                "Write text content to a workspace file.",
            ),
            "delete_file": (
                self._toolkit.delete_file,
                {"path"},
                {"permanent", "confirm"},
                "Delete a file or directory.",
            ),
            "copy_path": (
                self._toolkit.copy_path,
                {"source", "destination"},
                {"overwrite"},
                "Copy a workspace file or directory.",
            ),
            "move_path": (
                self._toolkit.move_path,
                {"source", "destination"},
                {"overwrite"},
                "Move a workspace file or directory.",
            ),
            "rename_path": (
                self._toolkit.rename_path,
                {"source", "new_name"},
                {"overwrite"},
                "Rename a workspace file or directory.",
            ),
            "search_files": (
                self._toolkit.search_files,
                {"pattern"},
                {"recursive"},
                "Search workspace filenames using a pattern.",
            ),
            "search_content": (
                self._toolkit.search_content,
                {"query"},
                {"file_pattern", "case_sensitive", "use_regex"},
                "Search file contents using literal text or regex.",
            ),
            "inspect_directory": (
                self._toolkit.inspect_directory,
                set(),
                {"path", "recursive", "max_depth"},
                "List entries in a workspace directory.",
            ),
            "inspect_metadata": (
                self._toolkit.inspect_metadata,
                {"path"},
                set(),
                "Inspect metadata for a workspace path.",
            ),
            "get_tree": (
                self._toolkit.get_tree,
                set(),
                {"path", "max_depth"},
                "Return a textual directory tree.",
            ),
        }

        registry: dict[str, OperationSpec] = {}

        for name, (
            handler,
            required,
            optional,
            description,
        ) in definitions.items():
            required_set = frozenset(required)
            optional_set = frozenset(optional)

            if required_set & optional_set:
                raise RuntimeError(f"Overlapping arguments in operation '{name}'.")

            registry[name] = OperationSpec(
                name=name,
                handler=handler,
                required_arguments=required_set,
                optional_arguments=optional_set,
                description=description,
            )

        return registry

    @property
    def available_operations(self) -> tuple[str, ...]:
        """Return all supported operation names."""

        return tuple(sorted(self._operations))

    def describe_operations(self) -> list[dict[str, Any]]:
        """Return JSON-serializable operation descriptions."""

        return [
            {
                "name": spec.name,
                "description": spec.description,
                "required_arguments": sorted(spec.required_arguments),
                "optional_arguments": sorted(spec.optional_arguments),
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
        """Validate and execute a registered filesystem operation."""

        if not isinstance(operation, str):
            raise FilesystemDispatchError("Operation name must be a string.")

        operation = operation.strip()

        if not operation:
            raise FilesystemDispatchError("Operation name cannot be empty.")

        spec = self._operations.get(operation)

        if spec is None:
            raise FilesystemDispatchError(f"Unsupported filesystem operation: {operation!r}.")

        if arguments is None:
            arguments = {}

        if not isinstance(arguments, Mapping):
            raise FilesystemDispatchError("Operation arguments must be a mapping.")

        supplied = set(arguments.keys())

        invalid_keys = [key for key in supplied if not isinstance(key, str) or not key]

        if invalid_keys:
            raise FilesystemDispatchError("All argument names must be non-empty strings.")

        missing = spec.required_arguments - supplied
        unknown = supplied - spec.allowed_arguments

        if missing:
            raise FilesystemDispatchError(
                f"Missing required arguments for '{operation}': {sorted(missing)}."
            )

        if unknown:
            raise FilesystemDispatchError(
                f"Unsupported arguments for '{operation}': {sorted(unknown)}."
            )

        try:
            result = spec.handler(**dict(arguments))
        except Exception as exc:
            raise FilesystemDispatchError(
                f"Filesystem operation '{operation}' failed: {type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(result, FilesystemToolResult):
            raise FilesystemDispatchError(f"Operation '{operation}' returned an invalid result.")

        return result
