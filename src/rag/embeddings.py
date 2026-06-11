from __future__ import annotations

import math
import re
from collections import Counter


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def embed_text(text: str, dimensions: int = 384) -> list[float]:
    """
    Dependency-free local embedding for MVP vector search.

    This uses a hashing vectorizer so the retriever behaves like vector search
    without requiring an external embedding model yet. It can later be replaced
    with Ollama embeddings or a hosted embedding API behind the same function.
    """
    counts = Counter(tokenize(text))
    vector = [0.0] * dimensions

    for token, count in counts.items():
        index = hash(token) % dimensions
        sign = -1.0 if hash(f"{token}:sign") % 2 else 1.0
        vector[index] += sign * (1.0 + math.log(count))

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector

    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
