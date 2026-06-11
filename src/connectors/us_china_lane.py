"""
US–China Lane Connector — fetches Port of Los Angeles cargo volumes, congestion
metrics, and operational briefings for the critical Shanghai–LA supply chain lane.

Sources:
  - Port of LA statistics: https://www.portoflosangeles.org/references/statistics
  - Port of LA press releases (RSS/news feed)
  - Optional Census trade data via CENSUS_API_KEY env var

Cadence: Weekly poll
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import requests

from src.connectors.base import (
    SourceConnector,
    RawDocument,
    DocumentType,
    ConnectorHealth,
)

logger = logging.getLogger(__name__)

POLA_URL = "https://www.portoflosangeles.org/references/statistics"

# Supply-chain keywords for filtering
_POLA_KEYWORDS = [
    "congestion", "dwell", "container", "volume", "teu", "import",
    "export", "berth", "terminal", "rail", "truck", "turnaround",
    "peak season", "capacity", "backlog", "china", "shanghai",
]


class USChinaLaneConnector(SourceConnector):
    """
    Monitors the Port of Los Angeles for supply chain metrics on the
    Shanghai–LA lane — the busiest US trade route with China.

    Config:
        name (str): Connector name. Default: "us-china-lane".
        simulate (bool): Force simulated data. Default: False.
        census_api_key (str): Optional Census API key for trade data.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.simulate: bool = config.get("simulate", False)
        self.census_api_key: str | None = config.get("census_api_key")

    # ── SourceConnector interface ──────────────────────────────────────

    def poll(self) -> list[RawDocument]:
        docs: list[RawDocument] = []

        # 1. Try live Port of LA data
        if not self.simulate:
            live = self._fetch_live()
            if live:
                docs.append(live)

        # 2. Try Census trade data if key is set
        if self.census_api_key:
            census = self._fetch_census_trade()
            if census:
                docs.append(census)

        # 3. Fall back to simulated signal if nothing live
        if not docs:
            logger.info("POLA live fetch failed — using simulated signal")
            docs.append(self._simulate_signal())

        return docs

    def acknowledge(self, source_id: str) -> None:
        pass  # Stateless

    def check_health(self) -> ConnectorHealth:
        try:
            resp = requests.get(POLA_URL, timeout=15)
            return ConnectorHealth(
                healthy=resp.ok or self.simulate,
                source=self.name,
                detail="Live" if resp.ok else "Simulated",
                document_count=1,
            )
        except requests.RequestException:
            return ConnectorHealth(
                healthy=True,
                source=self.name,
                detail="Simulated fallback",
                document_count=1,
            )

    # ── Live fetch ────────────────────────────────────────────────────

    def _fetch_live(self) -> RawDocument | None:
        try:
            resp = requests.get(POLA_URL, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SupplyChainBot/1.0)"
            })
            if not resp.ok:
                return None

            text = resp.text
            # Extract monthly TEU volume via regex (common pattern on POLA pages)
            teu_matches = re.findall(r"(\d{3},\d{3,})\s*(?:TEU|teu|containers)", text)
            volumes = [m[0] for m in teu_matches[:3]] if teu_matches else []

            # Check for congestion keywords
            congestion_keywords = [
                kw for kw in _POLA_KEYWORDS
                if re.search(rf"\b{kw}\b", text, re.I)
            ]

            data = {
                "source": "Port of Los Angeles",
                "url": POLA_URL,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "teu_volumes_found": volumes,
                "congestion_signals": congestion_keywords,
                "has_congestion": len(congestion_keywords) > 2,
            }
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")

            return RawDocument(
                source=self.name,
                source_id=f"pola_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                doc_type=DocumentType.PORT_UPDATE,
                raw_bytes=raw_bytes,
                filename="port_of_la_status.json",
                mime_type="application/json",
                received_at=datetime.now(timezone.utc),
                metadata={
                    "title": "Port of LA — Supply Chain Briefing",
                    "summary": f"TEU volumes: {volumes[0] if volumes else 'N/A'}. "
                               f"Congestion signals: {len(congestion_keywords)}",
                    "source_type": "Port Briefing",
                    "source_name": "Port of Los Angeles cargo briefing",
                },
            )
        except requests.RequestException as exc:
            logger.warning("POLA fetch error: %s", exc)
            return None

    def _fetch_census_trade(self) -> RawDocument | None:
        """Fetch US–China trade data from Census API if configured."""
        try:
            resp = requests.get(
                "https://api.census.gov/data/timeseries/int/trade",
                params={
                    "key": self.census_api_key,
                    "get": "CON_VAL_MO,CTY_NAME",
                    "CTY_CODE": "5700",  # China
                    "YEAR": datetime.now(timezone.utc).year,
                },
                timeout=15,
            )
            if resp.ok:
                data = resp.json()
                raw_bytes = json.dumps(data, indent=2).encode("utf-8")
                return RawDocument(
                    source=self.name,
                    source_id=f"census_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                    doc_type=DocumentType.PORT_UPDATE,
                    raw_bytes=raw_bytes,
                    filename="census_us_china_trade.json",
                    mime_type="application/json",
                    received_at=datetime.now(timezone.utc),
                    metadata={
                        "title": "US–China Trade Data (Census)",
                        "source_type": "Census Bureau",
                    },
                )
        except requests.RequestException:
            pass
        return None

    # ── Simulation ─────────────────────────────────────────────────────

    def _simulate_signal(self) -> RawDocument:
        data = {
            "source": "Port of Los Angeles (simulated)",
            "period": "Monthly",
            "total_teu": 825432,
            "year_over_year_change_pct": 4.2,
            "import_containers": 412000,
            "export_containers": 145000,
            "dwell_time_days": 4.8,
            "congestion_level": "MODERATE",
            "notable_issues": [
                "Extended dwell on Shanghai–LA vessels (5.2 days avg)",
                "Rail ramp congestion at ICTF",
                "Chassis availability improving",
            ],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": (
                "Port of LA processed 825k TEU this month (+4.2% YoY). "
                "Container dwell averaging 4.8 days with moderate congestion "
                "on Shanghai–LA lane."
            ),
        }
        raw_bytes = json.dumps(data, indent=2).encode("utf-8")
        return RawDocument(
            source=self.name,
            source_id=f"pola_sim_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            doc_type=DocumentType.PORT_UPDATE,
            raw_bytes=raw_bytes,
            filename="port_of_la_status.json",
            mime_type="application/json",
            received_at=datetime.now(timezone.utc),
            metadata={
                "title": "Port of LA — Simulated Supply Chain Briefing",
                "summary": data["summary"],
                "source_type": "Port Briefing",
                "source_name": "Port of Los Angeles cargo briefing (simulated)",
            },
        )