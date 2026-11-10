
"""Central workspace filesystem service for FORGEX."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forgex.tools.filesystem.deleter import FileDeleter
from forgex.tools.filesystem.directory import DirectoryInspector
from forgex.tools.filesystem.operations import FileOperations
from forgex.tools.filesystem.paths import WorkspacePathResolver
from forgex.tools.filesystem.protection import WorkspaceProtection
from forgex.tools.filesystem.reader import FileReader
from forgex.tools.filesystem.search import FileSearch
from forgex.tools.filesystem.writer import FileWriter


@dataclass(frozen=True, slots=True)
class WorkspaceConfiguration:
    """Configuration for a FORGEX workspace."""

    root: Path
    max_read_size: int = 10 * 1024 * 1024
    max_write_size: int = 10 * 1024 * 1024
    max_copy_size: int = 100 * 1024 * 1024
    max_directory_entries: int = 10_000
    allow_permanent_delete: bool = False
    allow_protected_reads: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "root",
            Path(self.root).expanduser().resolve(strict=True),
        )

        if not self.root.is_dir():
            raise ValueError("Workspace root must be a directory.")

        limits = (
            self.max_read_size,
            self.max_write_size,
            self.max_copy_size,
            self.max_directory_entries,
        )

        if any(value <= 0 for value in limits):
            raise ValueError("Workspace limits must be positive.")


class WorkspaceService:
    """Unified entry point for workspace filesystem operations."""

    def __init__(
        self,
        configuration: WorkspaceConfiguration,
        *,
        protected_patterns: tuple[str, ...] | None = None,
    ) -> None:
        if not isinstance(configuration, WorkspaceConfiguration):
            raise TypeError(
                "configuration must be WorkspaceConfiguration."
            )

        self._configuration = configuration

        self._resolver = WorkspacePathResolver(
            configuration.root,
        )

        self._protection = WorkspaceProtection(
            configuration.root,
            protected_patterns=protected_patterns,
            allow_read=configuration.allow_protected_reads,
        )

        self._reader = FileReader(
            self._resolver,
            max_file_size=configuration.max_read_size,
        )

        self._writer = FileWriter(
            self._resolver,
            protection=self._protection,
            max_write_size=configuration.max_write_size,
        )

        self._deleter = FileDeleter(
            self._resolver,
            protection=self._protection,
            allow_permanent_delete=configuration.allow_permanent_delete,
        )

        self._operations = FileOperations(
            self._resolver,
            protection=self._protection,
            max_copy_size=configuration.max_copy_size,
        )

        self._search = FileSearch(self._resolver)

        self._directory = DirectoryInspector(
            self._resolver,
            max_entries=configuration.max_directory_entries,
        )

    @property
    def root(self) -> Path:
        return self._configuration.root

    @property
    def resolver(self) -> WorkspacePathResolver:
        return self._resolver

    @property
    def protection(self) -> WorkspaceProtection:
        return self._protection

    @property
    def reader(self) -> FileReader:
        return self._reader

    @property
    def writer(self) -> FileWriter:
        return self._writer

    @property
    def deleter(self) -> FileDeleter:
        return self._deleter

    @property
    def operations(self) -> FileOperations:
        return self._operations

    @property
    def search(self) -> FileSearch:
        return self._search

    @property
    def directory(self) -> DirectoryInspector:
        return self._directory

    def inspect(self, path: str | Path = "."):
        """Inspect a workspace directory."""

        return self._directory.list_directory(path)

    def read(self, path: str | Path, **kwargs):
        """Read a workspace file."""

        result = self._resolver.resolve(
            path,
            must_exist=True,
            expected_type="file",
        )

        decision = self._protection.inspect(
            result.absolute,
            operation="read",
        )

        if not decision.allowed:
            raise PermissionError(decision.reason)

        return self._reader.read_text(path, **kwargs)

    def write(
        self,
        path: str | Path,
        content: str,
        **kwargs,
    ):
        """Write a workspace file."""

        return self._writer.write_text(
            path,
            content,
            **kwargs,
        )

    def delete(self, path: str | Path, **kwargs):
        """Delete a workspace entry recoverably by default."""

        return self._deleter.delete(path, **kwargs)

    def restore(self, deletion_result):
        """Restore a previously deleted workspace entry."""

        return self._deleter.restore(deletion_result)

    def copy(
        self,
        source: str | Path,
        destination: str | Path,
        **kwargs,
    ):
        """Copy a workspace entry."""

        return self._operations.copy(
            source,
            destination,
            **kwargs,
        )

    def move(
        self,
        source: str | Path,
        destination: str | Path,
        **kwargs,
    ):
        """Move a workspace entry."""

        return self._operations.move(
            source,
            destination,
            **kwargs,
        )

    def rename(
        self,
        source: str | Path,
        new_name: str,
        **kwargs,
    ):
        """Rename a workspace entry."""

        return self._operations.rename(
            source,
            new_name,
            **kwargs,
        )

    def find(self, *args, **kwargs):
        """Search workspace files."""

        return self._search.search_filenames(*args, **kwargs)

    def search_content(self, *args, **kwargs):
        """Search file contents."""

        return self._search.search_content(*args, **kwargs)

    def tree(self, path: str | Path = ".", **kwargs) -> str:
        """Return a directory tree."""

        return self._directory.tree(path, **kwargs)
