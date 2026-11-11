
"""Agent-facing filesystem toolkit for FORGEX."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from forgex.tools.filesystem.workspace import WorkspaceService


@dataclass(frozen=True, slots=True)
class FilesystemToolResult:
    """Normalized result returned to an agent."""

    operation: str
    success: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "success": self.success,
            "data": self.data,
            "error": self.error,
        }


class FilesystemToolkit:
    """Controlled filesystem operations exposed to FORGEX agents."""

    def __init__(self, workspace: WorkspaceService) -> None:
        if not isinstance(workspace, WorkspaceService):
            raise TypeError("workspace must be WorkspaceService.")

        self._workspace = workspace

    @property
    def workspace(self) -> WorkspaceService:
        return self._workspace

    def read_file(
        self,
        path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> FilesystemToolResult:
        return self._execute(
            "read_file",
            lambda: self._workspace.read(
                path,
                start_line=start_line,
                end_line=end_line,
            ),
        )

    def write_file(
        self,
        path: str,
        content: str,
        *,
        overwrite: bool = False,
    ) -> FilesystemToolResult:
        return self._execute(
            "write_file",
            lambda: self._workspace.write(
                path,
                content,
                overwrite=overwrite,
            ),
        )

    def delete_file(
        self,
        path: str,
        *,
        permanent: bool = False,
        confirm: bool = False,
    ) -> FilesystemToolResult:
        return self._execute(
            "delete_file",
            lambda: self._workspace.delete(
                path,
                permanent=permanent,
                confirm=confirm,
            ),
        )

    def copy_path(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = False,
    ) -> FilesystemToolResult:
        return self._execute(
            "copy_path",
            lambda: self._workspace.copy(
                source,
                destination,
                overwrite=overwrite,
            ),
        )

    def move_path(
        self,
        source: str,
        destination: str,
        *,
        overwrite: bool = False,
    ) -> FilesystemToolResult:
        return self._execute(
            "move_path",
            lambda: self._workspace.move(
                source,
                destination,
                overwrite=overwrite,
            ),
        )

    def rename_path(
        self,
        source: str,
        new_name: str,
        *,
        overwrite: bool = False,
    ) -> FilesystemToolResult:
        return self._execute(
            "rename_path",
            lambda: self._workspace.rename(
                source,
                new_name,
                overwrite=overwrite,
            ),
        )

    def search_files(
        self,
        pattern: str,
        *,
        recursive: bool = True,
        case_sensitive: bool = False,
        max_results: int | None = None,
    ) -> FilesystemToolResult:
        """Search filenames inside the workspace."""

        def operation():
            results = self._workspace.find(
                pattern,
                case_sensitive=case_sensitive,
                max_results=max_results,
            )

            if not recursive:
                root = self._workspace.root
                results = tuple(
                    path
                    for path in results
                    if Path(path).parent == root
                )

            return results

        return self._execute("search_files", operation)

    def search_content(
        self,
        query: str,
        *,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        use_regex: bool = False,
        max_results: int | None = None,
    ) -> FilesystemToolResult:
        """Search file contents using literal or regular expressions."""

        return self._execute(
            "search_content",
            lambda: self._workspace.search_content(
                query,
                file_pattern=file_pattern,
                case_sensitive=case_sensitive,
                regex=use_regex,
                max_results=max_results,
            ),
        )

    def inspect_directory(
        self,
        path: str = ".",
        *,
        recursive: bool = False,
        max_depth: int = 5,
    ) -> FilesystemToolResult:
        return self._execute(
            "inspect_directory",
            lambda: self._workspace.inspect(
                path,
                recursive=recursive,
                max_depth=max_depth,
            ),
        )

    def inspect_metadata(
        self,
        path: str,
    ) -> FilesystemToolResult:
        return self._execute(
            "inspect_metadata",
            lambda: self._workspace.inspect_metadata(path),
        )

    def get_tree(
        self,
        path: str = ".",
        *,
        max_depth: int = 3,
    ) -> FilesystemToolResult:
        return self._execute(
            "get_tree",
            lambda: self._workspace.tree(
                path,
                max_depth=max_depth,
            ),
        )

    def _execute(
        self,
        operation: str,
        callback: Callable[[], Any],
    ) -> FilesystemToolResult:
        try:
            result = callback()

            return FilesystemToolResult(
                operation=operation,
                success=True,
                data=self._serialize(result),
            )

        except Exception as exc:
            return FilesystemToolResult(
                operation=operation,
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    @classmethod
    def _serialize(cls, value: Any) -> Any:
        """Convert filesystem results into agent-friendly data."""

        if value is None or isinstance(
            value,
            (str, int, float, bool),
        ):
            return value

        if isinstance(value, Path):
            return str(value)

        if hasattr(value, "to_dict") and callable(value.to_dict):
            return cls._serialize(value.to_dict())

        if hasattr(value, "__dataclass_fields__"):
            return cls._serialize(asdict(value))

        if isinstance(value, dict):
            return {
                str(key): cls._serialize(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [cls._serialize(item) for item in value]

        return str(value)
