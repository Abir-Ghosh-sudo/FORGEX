"""Repository context engine for FORGEX.

Provides repository understanding, file/symbol retrieval, language-aware
parsing, context assembly, and search integration. Agents use this to build
task-specific prompts without sending entire repositories to models.
"""

from forgex.context.context_manager import ContextManager, ContextSnapshot
from forgex.context.file_retrieval import FileRetriever
from forgex.context.symbol_retrieval import SymbolRetriever
from forgex.context.context_assembler import ContextAssembler

__all__ = [
    "ContextManager",
    "ContextSnapshot",
    "FileRetriever",
    "SymbolRetriever",
    "ContextAssembler",
]
