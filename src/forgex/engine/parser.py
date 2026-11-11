"""Source code parsing engine for FORGEX."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from tree_sitter_language_pack import get_parser
except ImportError:
    get_parser = None


class ParserError(RuntimeError):
    """Raised when source parsing fails."""


@dataclass(frozen=True, slots=True)
class SyntaxNode:
    """Serializable representation of a syntax tree node."""

    node_type: str
    start_line: int
    end_line: int
    start_byte: int
    end_byte: int
    text: str
    named: bool = True
    children: tuple["SyntaxNode", ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Source parsing result."""

    file_path: str
    language: str
    root: SyntaxNode
    errors: tuple[SyntaxNode, ...] = ()
    success: bool = True


class SourceParser:
    """Parse source code using Tree-sitter."""

    EXTENSIONS: dict[str, str] = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".cs": "c_sharp",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".html": "html",
        ".css": "css",
        ".sql": "sql",
        ".sh": "bash",
    }

    def __init__(self, max_file_size: int = 5 * 1024 * 1024) -> None:
        if max_file_size <= 0:
            raise ValueError("max_file_size must be positive.")

        self.max_file_size = max_file_size

    def detect_language(self, file_path: str | Path) -> str | None:
        """Detect language from file extension."""
        return self.EXTENSIONS.get(Path(file_path).suffix.lower())

    def parse_file(
        self,
        file_path: str | Path,
        language: str | None = None,
    ) -> ParseResult:
        path = Path(file_path).expanduser().resolve()

        if not path.is_file():
            raise ParserError(f"File does not exist: {path}")

        if path.stat().st_size > self.max_file_size:
            raise ParserError(f"File exceeds size limit: {path}")

        detected = language or self.detect_language(path)

        if not detected:
            raise ParserError(f"Unsupported file type: {path.suffix}")

        try:
            source = path.read_bytes()
        except OSError as exc:
            raise ParserError(f"Unable to read file: {exc}") from exc

        return self.parse_source(
            source,
            language=detected,
            file_path=str(path),
        )

    def parse_source(
        self,
        source: str | bytes,
        language: str,
        file_path: str = "<memory>",
    ) -> ParseResult:
        """Parse source text and return a serializable syntax tree."""
        if get_parser is None:
            raise ParserError(
                "Tree-sitter language pack is not installed."
            )

        source_bytes = (
            source.encode("utf-8")
            if isinstance(source, str)
            else source
        )

        try:
            parser = get_parser(language)
            tree = parser.parse(source_bytes)
            root = self._convert_node(tree.root_node, source_bytes)
            errors = self._collect_errors(tree.root_node, source_bytes)

            return ParseResult(
                file_path=file_path,
                language=language,
                root=root,
                errors=errors,
                success=not tree.root_node.has_error,
            )

        except Exception as exc:
            if isinstance(exc, ParserError):
                raise
            raise ParserError(
                f"Failed to parse {language} source: {exc}"
            ) from exc

    def _convert_node(
        self,
        node: Any,
        source: bytes,
    ) -> SyntaxNode:
        """Convert Tree-sitter nodes into immutable Python objects."""
        text = source[node.start_byte:node.end_byte].decode(
            "utf-8",
            errors="replace",
        )

        return SyntaxNode(
            node_type=node.type,
            start_line=node.start_point.row + 1,
            end_line=node.end_point.row + 1,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            text=text,
            named=node.is_named,
            children=tuple(
                self._convert_node(child, source)
                for child in node.children
            ),
        )

    def _collect_errors(
        self,
        node: Any,
        source: bytes,
    ) -> tuple[SyntaxNode, ...]:
        """Collect syntax errors and missing nodes."""
        errors: list[SyntaxNode] = []

        def visit(current: Any) -> None:
            if current.type == "ERROR" or current.is_missing:
                errors.append(
                    self._convert_node(current, source)
                )

            for child in current.children:
                visit(child)

        visit(node)
        return tuple(errors)

    def get_symbols(
        self,
        result: ParseResult,
    ) -> tuple[SyntaxNode, ...]:
        """Extract common declaration nodes."""
        declaration_types = {
            "function_definition",
            "function_declaration",
            "class_definition",
            "class_declaration",
            "method_definition",
            "interface_declaration",
            "struct_item",
            "enum_item",
        }

        symbols: list[SyntaxNode] = []

        def visit(node: SyntaxNode) -> None:
            if node.node_type in declaration_types:
                symbols.append(node)

            for child in node.children:
                visit(child)

        visit(result.root)
        return tuple(symbols)