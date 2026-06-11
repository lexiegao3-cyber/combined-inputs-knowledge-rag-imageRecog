from pathlib import Path


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap

    return chunks


def load_knowledge_base(path: str = "knowledge_base") -> list[dict]:
    docs = []

    for file_path in Path(path).glob("*.md"):
        text = file_path.read_text(encoding="utf-8")
        for i, chunk in enumerate(chunk_text(text)):
            docs.append({
                "source": str(file_path),
                "chunk_id": f"{file_path.stem}-{i}",
                "text": chunk,
            })

    return docs