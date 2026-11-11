"""Unit tests for FORGEX memory layer."""

from __future__ import annotations

import pytest

from forgex.memory.memory_store import MemoryItem, MemorySearchResult
from forgex.memory.sqlite_store import SQLiteMemoryStore


class TestMemoryItem:
    def test_to_dict(self):
        item = MemoryItem(id="1", content="hi", memory_type="test")
        d = item.to_dict()
        assert d["id"] == "1"
        assert d["content"] == "hi"


class TestSQLiteMemoryStore:
    @pytest.mark.asyncio
    async def test_add_and_get(self, tmp_path):
        store = SQLiteMemoryStore(tmp_path / "test.db")
        item = MemoryItem(id="1", content="hello world", memory_type="note")
        await store.add(item)
        got = await store.get("1")
        assert got is not None
        assert got.content == "hello world"

    @pytest.mark.asyncio
    async def test_search(self, tmp_path):
        store = SQLiteMemoryStore(tmp_path / "test2.db")
        await store.add(MemoryItem(id="1", content="python coding", memory_type="note"))
        await store.add(MemoryItem(id="2", content="rust programming", memory_type="note"))
        results = await store.search("python", limit=5)
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_delete(self, tmp_path):
        store = SQLiteMemoryStore(tmp_path / "test3.db")
        await store.add(MemoryItem(id="1", content="temp", memory_type="note"))
        deleted = await store.delete("1")
        assert deleted is True
        got = await store.get("1")
        assert got is None

    @pytest.mark.asyncio
    async def test_clear(self, tmp_path):
        store = SQLiteMemoryStore(tmp_path / "test4.db")
        await store.add(MemoryItem(id="1", content="temp", memory_type="note"))
        cleared = await store.clear()
        assert cleared is True
