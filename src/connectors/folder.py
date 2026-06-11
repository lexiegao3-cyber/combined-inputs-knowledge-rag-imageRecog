"""
Folder Connector — scans a local directory for files.

This replaces and extends the old inline file-scanning logic that was baked
into ``ingest.py``. It implements the ``SourceConnector`` ABC so the ingestion
bus can treat it uniformly with any other connector.
"""

from __future__ import annotations

import glob
import hashlib
import logging
import os
import mimetypes
from datetime import datetime, timezone

from src.connectors.base import (
    SourceConnector,
    RawDocument,
    DocumentType,
    ConnectorHealth,
)

logger = logging.getLogger(__name__)

# Map file extensions to a rough document-type guess
_EXT_TO_DOC_TYPE: dict[str, DocumentType] = {
    ".pdf": DocumentType.SCAN,
    ".txt": DocumentType.OTHER,
    ".csv": DocumentType.INVENTORY_REPORT,
    ".xlsx": DocumentType.INVENTORY_REPORT,
    ".xlsm": DocumentType.INVENTORY_REPORT,
    ".docx": DocumentType.CONTRACT,
    ".json": DocumentType.OTHER,
    ".xml": DocumentType.OTHER,
    ".edi": DocumentType.CUSTOMS_FILING,
}


class FolderConnector(SourceConnector):
    """
    Polls a local directory (and subdirectories) for new files.

    Config:
        path (str): Directory to watch. Default: "./demo_inputs"
        recursive (bool): Scan subdirectories. Default: False
        seen_files (set): Internal — tracks already-processed files.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.folder_path: str = config.get("path", "./demo_inputs")
        self.recursive: bool = config.get("recursive", False)
        # In-memory set of seen file hashes. For production, persist this.
        self._seen_hashes: set[str] = set()

    # ── SourceConnector interface ──────────────────────────────────────

    def poll(self) -> list[RawDocument]:
        os.makedirs(self.folder_path, exist_ok=True)

        pattern = "**/*" if self.recursive else "*"
        discovered: list[str] = [
            f
            for f in glob.glob(os.path.join(self.folder_path, pattern))
            if os.path.isfile(f)
        ]

        docs: list[RawDocument] = []
        for file_path in discovered:
            file_hash = self._hash_file(file_path)
            if file_hash in self._seen_hashes:
                continue  # already processed

            filename = os.path.basename(file_path)
            ext = os.path.splitext(filename)[1].lower()
            doc_type = _EXT_TO_DOC_TYPE.get(ext)

            with open(file_path, "rb") as fh:
                raw_bytes = fh.read()

            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = "application/octet-stream"

            docs.append(RawDocument(
                source=self.name,
                source_id=file_hash,
                doc_type=doc_type,
                raw_bytes=raw_bytes,
                filename=filename,
                mime_type=mime_type,
                received_at=datetime.fromtimestamp(
                    os.path.getmtime(file_path), tz=timezone.utc
                ),
                metadata={
                    "file_path": file_path,
                    "file_size": len(raw_bytes),
                },
            ))

        return docs

    def acknowledge(self, source_id: str) -> None:
        self._seen_hashes.add(source_id)

    def check_health(self) -> ConnectorHealth:
        if not os.path.isdir(self.folder_path):
            return ConnectorHealth(
                healthy=False,
                source=self.name,
                detail=f"Directory not found: {self.folder_path}",
            )
        try:
            files = [
                f
                for f in os.listdir(self.folder_path)
                if os.path.isfile(os.path.join(self.folder_path, f))
            ]
            return ConnectorHealth(
                healthy=True,
                source=self.name,
                document_count=len(files),
            )
        except PermissionError as exc:
            return ConnectorHealth(
                healthy=False,
                source=self.name,
                detail=str(exc),
            )

    # ── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _hash_file(file_path: str) -> str:
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()