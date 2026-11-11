"""Search integration for context engine."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from forgex.context.file_retrieval import FileRetriever
from forgex.context.symbol_retrieval import SymbolRetriever

logger = logging.getLogger(__name__)


class ContextSearch:
    """Unified search over files, content, and symbols."""

    def __init__(self, workspace: str | Path) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.retriever = FileRetriever(self.workspace)
        self.symbols = SymbolRetriever(self.workspace)

    def search_files(
        self,
        pattern: str,
        *,
        recursive: bool = True,
        case_sensitive: bool = False,
        max_results: int | None = None,
    ) -> tuple[str, ...]:
        return self.retriever.find(
            pattern,
            case_sensitive=case_sensitive,
            max_results=max_results,
        )

    def search_content(
        self,
        query: str,
        *,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        regex: bool = False,
        max_results: int | None = None,
    ) -> tuple[str, ...]:
        return self.retriever.search_content(
            query,
            file_pattern=file_pattern,
            case_sensitive=case_sensitive,
            regex=regex,
            max_results=max_results,
        )

    def search_symbols(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self.symbols.search_symbol(query, limit=limit)

    def all_symbols(self) -> dict[str, list[dict[str, Any]]]:
        return self.symbols.scan_symbols()


__all__ = ["ContextSearch"]
