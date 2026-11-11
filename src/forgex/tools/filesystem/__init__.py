
"""FORGEX workspace filesystem tools."""

from forgex.tools.filesystem.paths import (
    ResolvedPath,
    WorkspacePathError,
    WorkspacePathResolver,
)
from forgex.tools.filesystem.reader import (
    FileReadError,
    FileReadResult,
    FileReader,
)
from forgex.tools.filesystem.writer import (
    FileWriteError,
    FileWritePermissionError,
    FileWriteResult,
    FileWriter,
)
from forgex.tools.filesystem.deleter import (
    FileDeletionError,
    FileDeletionResult,
    FileDeleter,
)
from forgex.tools.filesystem.search import (
    FileSearch,
    SearchMatch,
    SearchResult,
)
from forgex.tools.filesystem.directory import (
    DirectoryEntry,
    DirectoryInspector,
    DirectoryListing,
)
from forgex.tools.filesystem.operations import (
    FileOperationError,
    FileOperationResult,
    FileOperations,
)
from forgex.tools.filesystem.protection import (
    ProtectionResult,
    WorkspaceProtection,
)
from forgex.tools.filesystem.metadata import (
    FileMetadata,
    FileMetadataInspector,
)
from forgex.tools.filesystem.workspace import (
    WorkspaceConfiguration,
    WorkspaceService,
)
from forgex.tools.filesystem.toolkit import (
    FilesystemToolkit,
    FilesystemToolResult,
)
from forgex.tools.filesystem.dispatcher import (
    FilesystemDispatchError,
    FilesystemDispatcher,
    OperationSpec,
)

__all__ = [
    "ResolvedPath",
    "WorkspacePathError",
    "WorkspacePathResolver",
    "FileReadError",
    "FileReadResult",
    "FileReader",
    "FileWriteError",
    "FileWritePermissionError",
    "FileWriteResult",
    "FileWriter",
    "FileDeletionError",
    "FileDeletionResult",
    "FileDeleter",
    "FileSearch",
    "SearchMatch",
    "SearchResult",
    "DirectoryEntry",
    "DirectoryInspector",
    "DirectoryListing",
    "FileOperationError",
    "FileOperationResult",
    "FileOperations",
    "ProtectionResult",
    "WorkspaceProtection",
    "FileMetadata",
    "FileMetadataInspector",
    "WorkspaceConfiguration",
    "WorkspaceService",
    "FilesystemToolkit",
    "FilesystemToolResult",
    "FilesystemDispatchError",
    "FilesystemDispatcher",
    "OperationSpec",
]
