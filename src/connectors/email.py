"""
Email Connector — polls an email inbox (IMAP) for supply-chain related messages.

For MVP this works with any IMAP-accessible mailbox (Gmail, Office 365, etc.).
In production you'd swap to Gmail API / Graph API for higher rate limits.

Config
------
{
  "name": "email-scm",
  "host": "imap.gmail.com",
  "port": 993,
  "username": "supplychain@company.com",
  "password": "...",
  "mailbox": "INBOX",
  "search_criteria": ["UNSEEN"],
  "allowed_domains": ["@supplier.com", "@port-authority.gov"],
}
"""

from __future__ import annotations

import email
import logging
import imaplib
import re
from datetime import datetime, timezone
from typing import Any

from src.connectors.base import (
    SourceConnector,
    RawDocument,
    DocumentType,
    ConnectorHealth,
)

logger = logging.getLogger(__name__)

# Heuristics: guess doc type from subject / body keywords
_SUBJECT_TYPE_MAP: list[tuple[re.Pattern, DocumentType]] = [
    (re.compile(r"tariff|section\s?301|tariff\s?code|hs\s?code", re.I), DocumentType.TARIFF_NOTICE),
    (re.compile(r"bill\s?of\s?lading|bol|manifest", re.I), DocumentType.BILL_OF_LADING),
    (re.compile(r"port\s?congestion|port\s?status|berth|terminal", re.I), DocumentType.PORT_UPDATE),
    (re.compile(r"invoice", re.I), DocumentType.INVOICE),
    (re.compile(r"inventory|stock|warehouse", re.I), DocumentType.INVENTORY_REPORT),
    (re.compile(r"customs|clearance|customs\s?hold", re.I), DocumentType.CUSTOMS_FILING),
    (re.compile(r"contract|po\s?change|purchase\s?order", re.I), DocumentType.CONTRACT),
]


def _guess_doc_type(subject: str, body_snippet: str) -> DocumentType | None:
    """Simple keyword-based document type classification."""
    combined = f"{subject} {body_snippet[:500]}"
    for pattern, doc_type in _SUBJECT_TYPE_MAP:
        if pattern.search(combined):
            return doc_type
    return None


class EmailConnector(SourceConnector):
    """
    Polls an IMAP inbox for unread supply-chain emails.

    On ``poll()``:
      1. Connects via IMAP SSL
      2. Searches for unseen messages matching the configured criteria
      3. Downloads each message, extracts body + attachments, returns
         ``RawDocument`` objects
    On ``acknowledge(source_id)``:
      - Marks the email as SEEN (so it won't be returned again)

    Requires the ``imaplib`` standard library (no extra pip install).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self.host: str = config.get("host", "imap.gmail.com")
        self.port: int = config.get("port", 993)
        self.username: str = config["username"]
        self.password: str = config["password"]
        self.mailbox: str = config.get("mailbox", "INBOX")
        self.search_criteria: list[str] = config.get("search_criteria", ["UNSEEN"])
        self.allowed_domains: list[str] = config.get("allowed_domains", [])

    # ── SourceConnector interface ──────────────────────────────────────

    def poll(self) -> list[RawDocument]:
        try:
            imap = self._connect()
        except Exception as exc:
            logger.error("Email connector %s: connection failed: %s", self.name, exc)
            return []

        docs: list[RawDocument] = []
        try:
            imap.select(self.mailbox, readonly=True)

            search_str = " ".join(self.search_criteria) if self.search_criteria else "ALL"
            _status, msg_ids = imap.search(None, search_str)
            ids = msg_ids[0].split() if msg_ids[0] else []

            logger.info("Email connector %s: found %d new message(s)", self.name, len(ids))

            for uid in ids:
                _status, msg_data = imap.fetch(uid, "(RFC822)")
                if not msg_data or msg_data[0] is None:
                    continue

                raw_email = msg_data[0][1]
                parsed = email.message_from_bytes(raw_email)

                subject = parsed.get("Subject", "(no subject)")
                sender = parsed.get("From", "(unknown)")
                date_str = parsed.get("Date", "")

                # Optional domain filter
                if self.allowed_domains:
                    if not any(d in sender for d in self.allowed_domains):
                        continue

                # Extract text body
                body = self._get_text_body(parsed)

                doc_type = _guess_doc_type(subject, body[:1000])

                docs.append(RawDocument(
                    source=self.name,
                    source_id=uid.decode() if isinstance(uid, bytes) else str(uid),
                    doc_type=doc_type,
                    raw_bytes=raw_email,
                    filename=f"{subject[:80].strip()}.eml",
                    mime_type="message/rfc822",
                    received_at=self._parse_date(date_str),
                    metadata={
                        "subject": subject,
                        "from": sender,
                        "date": date_str,
                        "body_preview": body[:200],
                    },
                ))
        finally:
            try:
                imap.close()
                imap.logout()
            except Exception:
                pass

        return docs

    def acknowledge(self, source_id: str) -> None:
        """Mark an email as SEEN so polling won't return it again."""
        try:
            imap = self._connect()
            imap.select(self.mailbox, readonly=False)
            # source_id is the UID as a string
            imap.store(source_id, "+FLAGS", "\\SEEN")
            imap.close()
            imap.logout()
        except Exception as exc:
            logger.warning("Email connector %s: ack failed for %s: %s", self.name, source_id, exc)

    def check_health(self) -> ConnectorHealth:
        try:
            imap = self._connect()
            imap.select(self.mailbox, readonly=True)
            _status, msg_ids = imap.search(None, "ALL")
            count = len(msg_ids[0].split()) if msg_ids[0] else 0
            imap.close()
            imap.logout()
            return ConnectorHealth(
                healthy=True,
                source=self.name,
                document_count=count,
            )
        except Exception as exc:
            return ConnectorHealth(
                healthy=False,
                source=self.name,
                detail=str(exc),
            )

    # ── Internal helpers ───────────────────────────────────────────────

    def _connect(self) -> imaplib.IMAP4_SSL:
        imap = imaplib.IMAP4_SSL(self.host, self.port)
        imap.login(self.username, self.password)
        return imap

    @staticmethod
    def _get_text_body(msg: email.message.Message) -> str:
        """Extract plain-text body from an email Message tree."""
        if msg.is_multipart():
            parts = []
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            parts.append(payload.decode("utf-8", errors="replace"))
                    except Exception:
                        pass
            return "\n".join(parts)
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")
            return ""

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Best-effort email date parsing; fall back to now."""
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except Exception:
            return datetime.now(timezone.utc)