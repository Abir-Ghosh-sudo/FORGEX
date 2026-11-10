
"""FORGEX workspace filesystem infrastructure."""

from forgex.tools.filesystem.deleter import (
    FileDeleter,
    PermanentDeletionDenied,
    ProtectedDeletionError,
)
from forgex.tools.filesystem.directory import (
    DirectoryEntry,
    DirectoryInspector,
    DirectoryListing,
)
from forgex.tools.filesystem.metadata import (
    FileMetadata,
    FileMetadataInspector,
    MetadataInspectionError,
)
from forgex.tools.filesystem.operations import (
    FileOperations,
)
from forgex.tools.filesystem.paths import (
    ResolvedPath,
    WorkspacePathResolver,
)
from forgex.tools.filesystem.protection import (
    WorkspaceProtection,
)
from forgex.tools.filesystem.reader import (
    FileReader,
)
from forgex.tools.filesystem.search import (
    FileSearch,
    SearchMatch,
    SearchResult,
)
from forgex.tools.filesystem.writer import (
    FileWritePermissionError,
    FileWriter,
)
from forgex.tools.filesystem.workspace import (
    WorkspaceConfiguration,
    WorkspaceService,
)

__all__ = [
    "DirectoryEntry",
    "DirectoryInspector",
    "DirectoryListing",
    "FileDeleter",
    "FileMetadata",
    "FileMetadataInspector",
    "FileOperations",
    "FileReader",
    "FileSearch",
    "FileWritePermissionError",
    "FileWriter",
    "MetadataInspectionError",
    "PermanentDeletionDenied",
    "ProtectedDeletionError",
    "ResolvedPath",
    "SearchMatch",
    "SearchResult",
    "WorkspaceConfiguration",
    "WorkspacePathResolver",
    "WorkspaceProtection",
    "WorkspaceService",
]
