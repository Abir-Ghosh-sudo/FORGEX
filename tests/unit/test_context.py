"""Unit tests for FORGEX context layer."""

from __future__ import annotations

import pytest

from forgex.context.context_manager import ContextManager
from forgex.context.context_assembler import ContextAssembler
from forgex.context.file_retrieval import FileRetriever
from forgex.context.symbol_retrieval import SymbolRetriever
from forgex.context.parsers import detect_language, list_supported_languages, parse_file


class TestFileRetriever:
    def test_read_nonexistent(self, tmp_path):
        r = FileRetriever(tmp_path)
        with pytest.raises(FileNotFoundError):
            r.read("nonexistent.py")


class TestSymbolRetriever:
    def test_scan_symbols_empty(self, tmp_path):
        s = SymbolRetriever(tmp_path)
        syms = s.scan_symbols()
        assert isinstance(syms, dict)


class TestParsers:
    def test_detect_language_python(self):
        assert detect_language("foo.py") == "python"

    def test_detect_language_unknown(self):
        assert detect_language("foo.xyz") is None

    def test_list_languages(self):
        langs = list_supported_languages()
        assert "python" in langs


class TestContextAssembler:
    def test_assemble_empty(self, tmp_path):
        a = ContextAssembler(tmp_path)
        text = a.assemble(task="test", max_tokens=1024)
        assert "Task: test" in text
