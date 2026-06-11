from __future__ import annotations

from typing import Any

from src.rag.vector_store import get_vector_store


def retrieve_context(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    store = get_vector_store()
    return store.search(query, top_k=top_k)
