"""
Federal Register API Connector — polls the Federal Register for tariff notices
and returns activity counts (7-day and 30-day) for HS-code-related documents.

Source: https://www.federalregister.gov/api/v1
Cadence: Daily poll (notices + activity counts)
"""

from __future__ import annotations

import logging
import re
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from src.connectors.base import (
    SourceConnector,
    RawDocument,
    DocumentType,
    ConnectorHealth,
)

logger = logging.getLogger(__name__)

# Keywords that suggest a notice is tariff / trade related
_TARIFF_KEYWORDS = [
    "tariff", "duty", "import", "export", "trade", "section 301",
    "section 232", "harmonized tariff", "hts", "customs", "cbp",
    "trade remedy", "anti-dumping", "countervailing", "china",
    "exclusion", "tariff-rate quota",
]

BASE_URL = "https://www.federalregister.gov/api/v1"


class FederalRegisterConnector(SourceConnector):
    """
    Polls the Federal Register API for tariff/trade-related notices and
    aggregate activity metrics (7-day and 30-day counts).

    Config:
        api_key (str): Optional Federal Register API key.
        days_back (int): How many days to look back. Default: 7.
        name (str): Connector name. Default: "federal-register".
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.days_back: int = config.get("days_back", 7)
        self._seen_notices: set[str] = set()

    # ── SourceConnector interface ──────────────────────────────────────

    def poll(self) -> list[RawDocument]:
        docs: list[RawDocument] = []

        # 1. Fetch recent tariff-related notices
        notices = self._fetch_notices()
        for notice in notices:
            notice_id = notice.get("document_number", "")
            if notice_id in self._seen_notices:
                continue
            self._seen_notices.add(notice_id)

            raw_json = json.dumps(notice, indent=2).encode("utf-8")
            title = notice.get("title", "Untitled FR notice")[:80]
            pub_date = notice.get("publication_date", "")

            docs.append(RawDocument(
                source=self.name,
                source_id=notice_id,
                doc_type=DocumentType.TARIFF_NOTICE,
                raw_bytes=raw_json,
                filename=f"fr_{notice_id}.json",
                mime_type="application/json",
                received_at=self._parse_date(pub_date),
                metadata={
                    "title": title,
                    "document_number": notice_id,
                    "agency": notice.get("agency_names", [""])[0],
                    "fr_url": notice.get("html_url", ""),
                    "abstract": (notice.get("abstract", "") or "")[:500],
                },
            ))

        # 2. Fetch activity count metrics
        activity = self._fetch_activity_metrics()
        if activity is not None:
            raw_json = json.dumps(activity, indent=2).encode("utf-8")
            docs.append(RawDocument(
                source=self.name,
                source_id=f"activity_{datetime.now(timezone.utc).isoformat()}",
                doc_type=DocumentType.TARIFF_NOTICE,
                raw_bytes=raw_json,
                filename="fr_activity_metrics.json",
                mime_type="application/json",
                metadata={
                    "title": "Federal Register Activity Metrics",
                    "summary": f"7-day: {activity.get('count_7day', 0)} notices, "
                               f"30-day: {activity.get('count_30day', 0)} notices",
                },
            ))

        logger.info("FederalRegister: %d new notice(s), %d activity metric(s)",
                     len(docs) - (1 if activity else 0), 1 if activity else 0)
        return docs

    def acknowledge(self, source_id: str) -> None:
        self._seen_notices.add(source_id)

    def check_health(self) -> ConnectorHealth:
        try:
            resp = requests.get(f"{BASE_URL}/documents", params={"per_page": 1}, timeout=10)
            return ConnectorHealth(
                healthy=resp.ok,
                source=self.name,
                detail="API reachable" if resp.ok else f"HTTP {resp.status_code}",
                document_count=len(self._seen_notices),
            )
        except requests.RequestException as exc:
            return ConnectorHealth(
                healthy=False,
                source=self.name,
                detail=str(exc),
            )

    # ── Internal API calls ─────────────────────────────────────────────

    def _fetch_notices(self) -> list[dict]:
        """Fetch recent notices from the Federal Register API filtered for tariff keywords."""
        since = (datetime.now(timezone.utc) - timedelta(days=self.days_back)).strftime("%Y-%m-%d")

        params: dict[str, Any] = {
            "per_page": 100,
            "order": "newest",
            "conditions[publication_date][gte]": since,
        }

        # Build a search term from tariff keywords
        search_terms = " OR ".join(_TARIFF_KEYWORDS)
        params["conditions[term]"] = search_terms

        try:
            resp = requests.get(f"{BASE_URL}/documents", params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
        except requests.RequestException as exc:
            logger.warning("FederalRegister API error: %s", exc)
            return []

    def _fetch_activity_metrics(self) -> dict | None:
        """
        Fetch activity metrics: count of tariff-related notices in the
        last 7 days and last 30 days.
        """
        now = datetime.now(timezone.utc)
        metrics = {}

        for label, days in [("7day", 7), ("30day", 30)]:
            since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
            params = {
                "per_page": 0,  # don't need results, just count
                "conditions[publication_date][gte]": since,
                "conditions[term]": " OR ".join(_TARIFF_KEYWORDS),
            }
            try:
                resp = requests.get(f"{BASE_URL}/documents", params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                metrics[f"count_{label}"] = data.get("count", 0)
            except requests.RequestException as exc:
                logger.warning("FR activity metrics error (%s): %s", label, exc)
                metrics[f"count_{label}"] = -1

        if metrics.get("count_7day", -1) >= 0 and metrics.get("count_30day", -1) >= 0:
            metrics["fetched_at"] = now.isoformat()
            return metrics
        return None

    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        try:
            return datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)