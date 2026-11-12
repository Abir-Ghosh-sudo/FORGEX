"""Unit tests for FORGEX native C++ engine and Python fallback."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgex.engine.bindings import (
    is_native_available,
    load_native_engine,
)


class TestNativeEngine:
    """Verify native engine acceleration and capability reporting."""

    def test_native_availability(self) -> None:
        """Check native engine detection."""
        available = is_native_available()
        assert isinstance(available, bool)

    def test_load_native_engine(self) -> None:
        """Verify module loading returns a valid module or None fallback."""
        module = load_native_engine()
        if is_native_available():
            assert module is not None
            assert hasattr(module, "native_capabilities")
            caps = module.native_capabilities()
            assert isinstance(caps, dict)
            assert caps.get("core") is True
            assert caps.get("parser") is True
            assert caps.get("search") is True
            assert caps.get("indexing") is True
        else:
            pytest.skip("Native engine binary not available on this platform.")

    def test_native_capabilities_values(self) -> None:
        """Verify native capabilities keys when module is present."""
        module = load_native_engine()
        if module is None:
            pytest.skip("Native engine binary not available.")

        capabilities = module.native_capabilities()
        expected_keys = {"core", "parser", "search", "indexing", "persistent_index"}
        assert expected_keys.issubset(capabilities.keys())
        for key in expected_keys:
            assert capabilities[key] is True

    def test_core_parser_and_search_bindings(self) -> None:
        """Exercise core, parser and search APIs through pybind11."""
        module = load_native_engine()
        if module is None:
            pytest.skip("Native engine binary not available.")

        info = module.CoreEngine.get_info()
        assert info.name == "FORGEX"
        assert info.cpp_standard == 202002

        stats = module.CoreEngine.analyze_text("hello world\nFORGEX")
        assert stats.words == 3
        assert stats.lines == 2

        parsed = module.SourceParser().parse(
            "def greet():\n    return 1\n",
            "python",
        )
        assert parsed.success is True
        assert parsed.language == "python"
        assert parsed.tokens

        options = module.SearchOptions()
        options.case_sensitive = False
        search = module.CodeSearchEngine().search_text(
            "Alpha\nalpha\n",
            "ALPHA",
            options,
            "sample.py",
        )
        assert search.success is True
        assert search.total_matches == 2
        assert search.matches[0].file_path == "sample.py"

    def test_indexing_and_persistent_store_bindings(self, tmp_path: Path) -> None:
        """Exercise filesystem path conversion, indexing and index persistence."""
        module = load_native_engine()
        if module is None:
            pytest.skip("Native engine binary not available.")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "alpha.py").write_text(
            "def alpha():\n    return 1\n",
            encoding="utf-8",
        )
        (workspace / "beta.txt").write_text("beta\n", encoding="utf-8")

        indexer = module.RepositoryIndexer()
        options = module.IndexOptions()
        options.extensions = [".py"]
        result = indexer.index_directory(workspace, options)

        assert result.success is True
        assert result.indexed_count == 1
        assert indexer.file_count() == 1
        assert indexer.get_file("alpha.py").path == "alpha.py"

        store = module.IndexStore(tmp_path / "cache")
        files = indexer.get_all_files()
        assert store.save(files) is True
        loaded = store.load()
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded[0].content == files[0].content
