"""
Source Connector ABC — pluggable ingestion source interface.

All data sources (local folder, email, SFTP, S3, webhooks) implement this
protocol so the ingestion bus can discover, poll, and acknowledge documents
in a uniform way.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class DocumentType(str, Enum):
    """Categorises an ingested document for downstream routing."""
    EMAIL = "EMAIL"
    BILL_OF_LADING = "BILL_OF_LADING"
    TARIFF_NOTICE = "TARIFF_NOTICE"
    PORT_UPDATE = "PORT_UPDATE"
    INVOICE = "INVOICE"
    INVENTORY_REPORT = "INVENTORY_REPORT"
    CUSTOMS_FILING = "CUSTOMS_FILING"
    CONTRACT = "CONTRACT"
    SCAN = "SCAN"
    OTHER = "OTHER"


@dataclass
class RawDocument:
    """
    One document discovered by a SourceConnector, carrying enough metadata
    for the ingestion bus to deduplicate, parse, and acknowledge it.
    """
    source: str                          # connector name, e.g. "folder", "email"
    source_id: str                       # unique ID within that source (file path, email UID, etc.)
    doc_type: DocumentType | None        # best-guess before parsing; None = needs classification
    raw_bytes: bytes                     # original payload
    filename: str                        # display name / original filename
    mime_type: str                       # e.g. "text/plain", "application/pdf", "message/rfc822"
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorHealth:
    """Returned by ``SourceConnector.check_health()``."""
    healthy: bool
    source: str
    detail: str = ""
    document_count: int = 0


class SourceConnector(ABC):
    """
    Abstract base for a pluggable data source.
    
    Three methods to implement:
        poll()     → return newly available documents
        ack(id_)   → mark a document as processed (so it won't be returned again)
        health()   → return connectivity / status info
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name: str = config.get("name", self.__class__.__name__)
        logger.info("Initialised connector %s", self.name)

    @abstractmethod
    def poll(self) -> list[RawDocument]:
        """Return all unprocessed documents currently available."""

    @abstractmethod
    def acknowledge(self, source_id: str) -> None:
        """Mark a document (by source_id) as processed — it won't be polled again."""

    @abstractmethod
    def check_health(self) -> ConnectorHealth:
        """Return connectivity / status."""