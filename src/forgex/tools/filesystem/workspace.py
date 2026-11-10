
"""Central workspace filesystem service for FORGEX."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from forgex.tools.filesystem.deleter import FileDeleter
from forgex.tools.filesystem.directory import DirectoryInspector
from forgex.tools.filesystem.metadata import FileMetadataInspector
from forgex.tools.filesystem.operations import FileOperations
from forgex.tools.filesystem.paths import WorkspacePathResolver
from forgex.tools.filesystem.protection import WorkspaceProtection
from forgex.tools.filesystem.reader import FileReader
from forgex.tools.filesystem.search import FileSearch
from forgex.tools.filesystem.writer import FileWriter


class WorkspaceConfiguration:
    """Validated configuration for a FORGEX workspace."""

    def __init__(
        self,
        root: str | Path,
        *,
        max_read_size: int = 10 * 1024 * 1024,
        max_write_size: int = 10 * 1024 * 1024,
        max_copy_size: int = 100 * 1024 * 1024,
        max_directory_entries: int = 10_000,
        allow_permanent_delete: bool = False,
        allow_protected_reads: bool = True,
    ) -> None:
        self.root = Path(root).expanduser().resolve(strict=True)

        if not self.root.is_dir():
            raise ValueError("Workspace root must be a directory.")

        limits = (
            max_read_size,
            max_write_size,
            max_copy_size,
            max_directory_entries,
        )

        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            for value in limits
        ):
            raise ValueError("Workspace limits must be positive integers.")

        self.max_read_size = max_read_size
        self.max_write_size = max_write_size
        self.max_copy_size = max_copy_size
        self.max_directory_entries = max_directory_entries
        self.allow_permanent_delete = allow_permanent_delete
        self.allow_protected_reads = allow_protected_reads


class WorkspaceService:
    """Unified filesystem API with shared workspace protection."""

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

        self._metadata = FileMetadataInspector(
            self._resolver,
            protection=self._protection,
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

    @property
    def metadata(self) -> FileMetadataInspector:
        return self._metadata

    def inspect(self, path: str | Path = "."):
        return self._directory.list_directory(path)

    def inspect_metadata(
        self,
        path: str | Path,
        *,
        allow_protected_read: bool = False,
    ):
        return self._metadata.inspect(
            path,
            allow_protected_read=allow_protected_read,
        )

    def read(self, path: str | Path, **kwargs: Any):
        resolved = self._resolver.resolve(
            path,
            must_exist=True,
            expected_type="file",
        )

        decision = self._protection.inspect(
            resolved.absolute,
            operation="read",
        )

        if not decision.allowed:
            raise PermissionError(decision.reason)

        return self._reader.read_text(path, **kwargs)

    def write(
        self,
        path: str | Path,
        content: str,
        **kwargs: Any,
    ):
        return self._writer.write_text(
            path,
            content,
            **kwargs,
        )

    def delete(self, path: str | Path, **kwargs: Any):
        return self._deleter.delete(path, **kwargs)

    def restore(self, deletion_result):
        return self._deleter.restore(deletion_result)

    def copy(
        self,
        source: str | Path,
        destination: str | Path,
        **kwargs: Any,
    ):
        return self._operations.copy(
            source,
            destination,
            **kwargs,
        )

    def move(
        self,
        source: str | Path,
        destination: str | Path,
        **kwargs: Any,
    ):
        return self._operations.move(
            source,
            destination,
            **kwargs,
        )

    def rename(
        self,
        source: str | Path,
        new_name: str,
        **kwargs: Any,
    ):
        return self._operations.rename(
            source,
            new_name,
            **kwargs,
        )

    def find(self, *args: Any, **kwargs: Any):
        return self._search.search_filenames(*args, **kwargs)

    def search_content(self, *args: Any, **kwargs: Any):
        return self._search.search_content(*args, **kwargs)

    def tree(self, path: str | Path = ".", **kwargs: Any) -> str:
        return self._directory.tree(path, **kwargs)
