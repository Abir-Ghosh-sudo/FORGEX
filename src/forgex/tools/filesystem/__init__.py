
"""FORGEX workspace filesystem tools."""

from forgex.tools.filesystem.deleter import (
    FileDeleter,
    FileDeletionError,
    FileDeletionResult,
    PermanentDeletionDenied,
    ProtectedDeletionError,
)
from forgex.tools.filesystem.directory import (
    DirectoryEntry,
    DirectoryInspector,
    DirectoryListing,
    DirectoryOperationError,
)
from forgex.tools.filesystem.operations import (
    DestinationExistsError,
    FileOperationError,
    FileOperationResult,
    FileOperations,
    InvalidOperationError,
    ProtectedFileOperationError,
)
from forgex.tools.filesystem.paths import (
    PathResolutionError,
    ResolvedPath,
    WorkspacePathResolver,
)
from forgex.tools.filesystem.protection import (
    ProtectionError,
    ProtectionResult,
    ProtectedPathError,
    WorkspaceProtection,
)
from forgex.tools.filesystem.reader import (
    FileReadError,
    FileReadResult,
    FileReader,
)
from forgex.tools.filesystem.search import (
    FileSearch,
    SearchMatch,
    SearchResult,
)
from forgex.tools.filesystem.writer import (
    FileWriteError,
    FileWritePermissionError,
    FileWriteResult,
    FileWriter,
)
from forgex.tools.filesystem.workspace import (
    WorkspaceConfiguration,
    WorkspaceService,
)

__all__ = [
    "DestinationExistsError",
    "DirectoryEntry",
    "DirectoryInspector",
    "DirectoryListing",
    "DirectoryOperationError",
    "FileDeleter",
    "FileDeletionError",
    "FileDeletionResult",
    "FileOperationError",
    "FileOperationResult",
    "FileOperations",
    "FileReadError",
    "FileReadResult",
    "FileReader",
    "FileSearch",
    "FileWriteError",
    "FileWritePermissionError",
    "FileWriteResult",
    "FileWriter",
    "InvalidOperationError",
    "PathResolutionError",
    "PermanentDeletionDenied",
    "ProtectionError",
    "ProtectionResult",
    "ProtectedDeletionError",
    "ProtectedFileOperationError",
    "ProtectedPathError",
    "ResolvedPath",
    "SearchMatch",
    "SearchResult",
    "WorkspaceConfiguration",
    "WorkspacePathResolver",
    "WorkspaceProtection",
    "WorkspaceService",
]
