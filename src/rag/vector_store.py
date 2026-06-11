from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.rag.chunking import load_knowledge_base
from src.rag.embeddings import cosine_similarity, embed_text


@dataclass
class VectorRecord:
    source: str
    chunk_id: str
    text: str
    embedding: list[float]


class InMemoryVectorStore:
    def __init__(self, records: list[VectorRecord]) -> None:
        self.records = records

    @classmethod
    def from_knowledge_base(cls, path: str = "knowledge_base") -> "InMemoryVectorStore":
        records = []
        for doc in load_knowledge_base(path):
            records.append(
                VectorRecord(
                    source=doc["source"],
                    chunk_id=doc["chunk_id"],
                    text=doc["text"],
                    embedding=embed_text(doc["text"]),
                )
            )
        return cls(records)

    def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        query_embedding = embed_text(query)
        scored = []

        for record in self.records:
            score = cosine_similarity(query_embedding, record.embedding)
            scored.append((score, record))

        scored.sort(key=lambda item: item[0], reverse=True)

        results = []
        for score, record in scored[:top_k]:
            if score <= 0:
                continue
            results.append(
                {
                    "source": record.source,
                    "chunk_id": record.chunk_id,
                    "text": record.text,
                    "score": score,
                }
            )
        return results


_STORE_CACHE: InMemoryVectorStore | None = None


def get_vector_store(path: str = "knowledge_base") -> InMemoryVectorStore:
    global _STORE_CACHE
    if _STORE_CACHE is None:
        _STORE_CACHE = InMemoryVectorStore.from_knowledge_base(path)
    return _STORE_CACHE
