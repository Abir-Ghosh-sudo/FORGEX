"""Local-first retrieval augmented generation utilities for FORGEX.

The vector backend and embedding model are injected by the caller. Chroma and
LangChain integrations are optional; this module has no mandatory heavy deps.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from forgex.context.file_retrieval import FileRetriever


class EmbeddingFunction(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    text: str
    source: str
    chunk_index: int
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "source": self.source,
                "chunk_index": self.chunk_index, "score": self.score}


def chunk_text(text: str, *, chunk_size: int = 1200, chunk_overlap: int = 160) -> list[str]:
    """Split text into deterministic character windows with overlap."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive.")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size.")
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        if end < len(normalized):
            boundary = normalized.rfind("\n", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks


class ChromaRAG:
    """Workspace document index and similarity retriever backed by Chroma."""

    def __init__(
        self,
        workspace: str | Path,
        embeddings: EmbeddingFunction,
        *,
        collection_name: str = "forgex_repository",
        persist_directory: str | Path | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 160,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        if not self.workspace.is_dir():
            raise NotADirectoryError(f"Workspace does not exist or is not a directory: {self.workspace}")
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError("Chroma RAG requires the optional dependency: pip install 'forgex-ai[vector]'") from exc
        self.embeddings = embeddings
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.retriever = FileRetriever(self.workspace)
        self.client = chromadb.PersistentClient(path=str(persist_directory)) if persist_directory else chromadb.Client()
        self.collection = self.client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

    def ingest(self, paths: list[str] | None = None) -> int:
        """Chunk and upsert workspace files; returns number of indexed chunks."""
        selected = paths if paths is not None else list(self.retriever.find("*"))
        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict[str, Any]] = []
        for rel in selected:
            path = (self.workspace / rel).resolve()
            if not path.is_relative_to(self.workspace) or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for index, chunk in enumerate(chunk_text(content, chunk_size=self.chunk_size,
                                                       chunk_overlap=self.chunk_overlap)):
                digest = hashlib.sha256(f"{rel}:{index}:{chunk}".encode()).hexdigest()
                ids.append(digest)
                docs.append(chunk)
                metas.append({"source": str(path.relative_to(self.workspace)), "chunk_index": index})
        if not docs:
            return 0
        vectors = self.embeddings.embed_documents(docs)
        if len(vectors) != len(docs):
            raise ValueError("Embedding provider returned a different number of vectors than documents.")
        self.collection.upsert(ids=ids, documents=docs, embeddings=vectors, metadatas=metas)
        return len(docs)

    def retrieve(self, query: str, *, top_k: int = 5) -> list[RetrievedChunk]:
        """Return most relevant chunks, with repository-relative source metadata."""
        if not query.strip():
            raise ValueError("Query cannot be empty.")
        if top_k < 1:
            raise ValueError("top_k must be positive.")
        if self.collection.count() == 0:
            return []
        result = self.collection.query(
            query_embeddings=[self.embeddings.embed_query(query)],
            n_results=min(top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        return [
            RetrievedChunk(text=doc, source=meta.get("source", ""),
                           chunk_index=int(meta.get("chunk_index", 0)),
                           score=1.0 - float(distances[i]) if i < len(distances) else None)
            for i, (doc, meta) in enumerate(zip(docs, metas))
        ]

    def build_context(self, query: str, *, top_k: int = 5) -> str:
        """Format retrieved chunks with explicit source labels for grounding."""
        chunks = self.retrieve(query, top_k=top_k)
        if not chunks:
            return "No relevant repository context was found."
        return "\n\n".join(
            f"[Source: {item.source} | chunk {item.chunk_index}]\n{item.text}"
            for item in chunks
        )


__all__ = ["ChromaRAG", "EmbeddingFunction", "RetrievedChunk", "chunk_text"]
