"""Native C++ engine binding package."""

from __future__ import annotations

try:
    from forgex._native import (
        CoreEngine,
        EngineInfo,
        TextStatistics,
        TokenType,
        Token,
        ParseError,
        ParseResult,
        SourceParser,
        SearchOptions,
        SearchMatch,
        SearchResult,
        CodeSearchEngine,
        IndexOptions,
        IndexedFile,
        IndexingError,
        IndexingResult,
        RepositoryIndexer,
        IndexStore,
        native_capabilities,
    )

    NATIVE_AVAILABLE = True

except ImportError:
    NATIVE_AVAILABLE = False

    CoreEngine = None
    EngineInfo = None
    TextStatistics = None
    TokenType = None
    Token = None
    ParseError = None
    ParseResult = None
    SourceParser = None
    SearchOptions = None
    SearchMatch = None
    SearchResult = None
    CodeSearchEngine = None
    IndexOptions = None
    IndexedFile = None
    IndexingError = None
    IndexingResult = None
    RepositoryIndexer = None
    IndexStore = None
    native_capabilities = None


__all__ = [
    "NATIVE_AVAILABLE",
    "CoreEngine",
    "EngineInfo",
    "TextStatistics",
    "TokenType",
    "Token",
    "ParseError",
    "ParseResult",
    "SourceParser",
    "SearchOptions",
    "SearchMatch",
    "SearchResult",
    "CodeSearchEngine",
    "IndexOptions",
    "IndexedFile",
    "IndexingError",
    "IndexingResult",
    "RepositoryIndexer",
    "IndexStore",
    "native_capabilities",
]