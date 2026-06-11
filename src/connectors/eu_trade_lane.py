"""
EU–US Trade Lane Connector — fetches Port of Rotterdam news, Eurostat trade
metrics, and congestion data for the Europe–US supply chain lane.

Sources:
  - Port of Rotterdam news: https://www.portofrotterdam.com/en/news
  - Eurostat US–EU trade: https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data
  - Eurostat ext_lt_maineu: annual EU↔US trade metrics

Cadence: Weekly poll (rotating through sources)
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

ROTTERDAM_NEWS_URL = "https://www.portofrotterdam.com/en/news"
EUROSTAT_TRADE_URL = (
    "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
    "ext_lt_maineu?format=JSON&precision=1&unit=MIO_EUR&partner=US&geo=EU27_2020"
)

# Keywords for filtering Rotterdam news for supply chain relevance
_RDAM_KEYWORDS = [
    "container", "volume", "congestion", "delay", "capacity",
    "terminal", "rail", "barge", "energy", "chemical", "biomass",
    "sustainability", "digital", "breakbulk", "agribulk", "supply chain",
]


class EUTradeLaneConnector(SourceConnector):
    """
    Monitors the Europe–US trade lane via Port of Rotterdam news and
    Eurostat trade statistics (EU exports/imports with the US).

    Config:
        name (str): Connector name. Default: "eu-trade-lane".
        simulate (bool): Force simulated data. Default: False.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.simulate: bool = config.get("simulate", False)

    # ── SourceConnector interface ──────────────────────────────────────

    def poll(self) -> list[RawDocument]:
        docs: list[RawDocument] = []

        # 1. Try Eurostat trade data
        if not self.simulate:
            eurostat = self._fetch_eurostat()
            if eurostat:
                docs.append(eurostat)

            rdam = self._fetch_rotterdam_news()
            if rdam:
                docs.append(rdam)

        # 2. Fall back to simulated signals
        if not docs:
            logger.info("EU trade lane live fetch failed — using simulated signals")
            docs.append(self._simulate_trade_signal())
            docs.append(self._simulate_port_signal())

        return docs

    def acknowledge(self, source_id: str) -> None:
        pass  # Stateless

    def check_health(self) -> ConnectorHealth:
        try:
            resp = requests.get(EUROSTAT_TRADE_URL, timeout=15)
            return ConnectorHealth(
                healthy=resp.ok or self.simulate,
                source=self.name,
                detail="Live" if resp.ok else "Simulated",
                document_count=2,
            )
        except requests.RequestException:
            return ConnectorHealth(
                healthy=True,
                source=self.name,
                detail="Simulated fallback",
                document_count=2,
            )

    # ── Live fetches ──────────────────────────────────────────────────

    def _fetch_eurostat(self) -> RawDocument | None:
        try:
            resp = requests.get(EUROSTAT_TRADE_URL, timeout=20)
            if not resp.ok:
                return None

            data = resp.json()
            # Extract the value dimension
            values = data.get("value", {})
            dimensions = data.get("dimension", {})

            # Find latest year with data
            year_dim = dimensions.get("TIME_PERIOD", {})
            years = year_dim.get("category", {}).get("index", {})
            latest_year = max(years.keys()) if years else "N/A"

            # Sum all values for EU–US trade
            total_trade = sum(
                v for v in values.values() if isinstance(v, (int, float))
            )

            result = {
                "source": "Eurostat",
                "dataset": "ext_lt_maineu",
                "partner": "United States",
                "geo": "EU27_2020",
                "latest_year": latest_year,
                "total_bilateral_trade_mio_eur": round(total_trade, 0),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "summary": (
                    f"EU–US bilateral trade: \u20ac{total_trade:,.0f} million "
                    f"(latest: {latest_year})"
                ),
            }
            raw_bytes = json.dumps(result, indent=2).encode("utf-8")
            return RawDocument(
                source=self.name,
                source_id=f"eurostat_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                doc_type=DocumentType.PORT_UPDATE,
                raw_bytes=raw_bytes,
                filename="eurostat_us_eu_trade.json",
                mime_type="application/json",
                received_at=datetime.now(timezone.utc),
                metadata={
                    "title": "EU–US Trade Statistics (Eurostat)",
                    "summary": result["summary"],
                    "source_type": "Eurostat",
                    "source_name": "Eurostat ext_lt_maineu",
                },
            )
        except requests.RequestException as exc:
            logger.warning("Eurostat fetch error: %s", exc)
            return None

    def _fetch_rotterdam_news(self) -> RawDocument | None:
        """Scrape Port of Rotterdam news page for supply chain signals."""
        try:
            resp = requests.get(ROTTERDAM_NEWS_URL, timeout=20, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SupplyChainBot/1.0)"
            })
            if not resp.ok:
                return None

            text = resp.text
            # Find supply chain keywords in the page
            found_keywords = [
                kw for kw in _RDAM_KEYWORDS
                if re.search(rf"\b{kw}\b", text, re.I)
            ]

            data = {
                "source": "Port of Rotterdam",
                "url": ROTTERDAM_NEWS_URL,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "relevant_keywords": found_keywords,
                "signal_strength": len(found_keywords),
            }
            raw_bytes = json.dumps(data, indent=2).encode("utf-8")
            return RawDocument(
                source=self.name,
                source_id=f"rdam_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                doc_type=DocumentType.PORT_UPDATE,
                raw_bytes=raw_bytes,
                filename="port_of_rotterdam_signal.json",
                mime_type="application/json",
                received_at=datetime.now(timezone.utc),
                metadata={
                    "title": "Port of Rotterdam — Supply Chain Signals",
                    "summary": f"{len(found_keywords)} supply chain signals detected",
                    "source_type": "Port Briefing",
                    "source_name": "Port of Rotterdam news feed",
                },
            )
        except requests.RequestException as exc:
            logger.warning("Rotterdam fetch error: %s", exc)
            return None

    # ── Simulation ─────────────────────────────────────────────────────

    def _simulate_trade_signal(self) -> RawDocument:
        data = {
            "source": "Eurostat (simulated)",
            "dataset": "ext_lt_maineu",
            "partner": "United States",
            "geo": "EU27_2020",
            "latest_year": 2025,
            "total_bilateral_trade_mio_eur": 685000,
            "eu_exports_to_us_mio_eur": 415000,
            "eu_imports_from_us_mio_eur": 270000,
            "trade_surplus_mio_eur": 145000,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": (
                "EU–US bilateral trade estimated at \u20ac685B (2025). "
                "EU exports to US: \u20ac415B (+3.2% YoY). "
                "Chemicals and machinery lead growth."
            ),
        }
        raw_bytes = json.dumps(data, indent=2).encode("utf-8")
        return RawDocument(
            source=self.name,
            source_id=f"eurostat_sim_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            doc_type=DocumentType.PORT_UPDATE,
            raw_bytes=raw_bytes,
            filename="eurostat_us_eu_trade.json",
            mime_type="application/json",
            received_at=datetime.now(timezone.utc),
            metadata={
                "title": "EU–US Trade (Simulated)",
                "summary": data["summary"],
                "source_type": "Eurostat",
                "source_name": "Eurostat ext_lt_maineu (simulated)",
            },
        )

    def _simulate_port_signal(self) -> RawDocument:
        data = {
            "source": "Port of Rotterdam (simulated)",
            "total_throughput_mt": 467.0,
            "container_teu_millions": 14.5,
            "year_over_year_change_pct": 1.8,
            "congestion_level": "LOW",
            "notable_trends": [
                "Energy transition driving biomass and hydrogen imports",
                "Container volumes stable with slight growth in Asia–EU transshipment",
                "Chemical cluster operating at 88% capacity",
            ],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "summary": (
                "Port of Rotterdam throughput steady at 467M tonnes (+1.8% YoY). "
                "Container volumes stable. Low congestion on EU–US lanes."
            ),
        }
        raw_bytes = json.dumps(data, indent=2).encode("utf-8")
        return RawDocument(
            source=self.name,
            source_id=f"rdam_sim_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            doc_type=DocumentType.PORT_UPDATE,
            raw_bytes=raw_bytes,
            filename="port_of_rotterdam_signal.json",
            mime_type="application/json",
            received_at=datetime.now(timezone.utc),
            metadata={
                "title": "Port of Rotterdam — Simulated Update",
                "summary": data["summary"],
                "source_type": "Port Briefing",
                "source_name": "Port of Rotterdam (simulated)",
            },
        )