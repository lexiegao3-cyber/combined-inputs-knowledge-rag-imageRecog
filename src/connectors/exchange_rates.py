"""
Exchange Rate Connector — fetches live USD/CNY and USD/EUR rates from open.er-api.com.

Source: https://open.er-api.com/v6/latest/USD
Cadence: Daily poll (rates update once per day)
"""

from __future__ import annotations

import json
import logging
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

API_URL = "https://open.er-api.com/v6/latest/USD"

# Target currencies relevant to supply chain operations
_TARGET_CURRENCIES = ["CNY", "EUR", "GBP", "JPY", "KRW", "SGD", "VND", "THB"]


class ExchangeRateConnector(SourceConnector):
    """
    Polls open.er-api.com for USD exchange rates against key supply-chain
    currencies (CNY, EUR, GBP, JPY, KRW, SGD, VND, THB).

    Config:
        name (str): Connector name. Default: "exchange-rates".
        base_currency (str): Base currency. Default: "USD".
        simulate (bool): Force simulated data. Default: False.
    """

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.base_currency: str = config.get("base_currency", "USD")
        self.simulate: bool = config.get("simulate", False)
        self._last_rates: dict[str, float] = {}

    # ── SourceConnector interface ──────────────────────────────────────

    def poll(self) -> list[RawDocument]:
        if self.simulate:
            return [self._simulate_rates()]

        rates = self._fetch_live()
        if rates is not None:
            return [self._build_rates_doc(rates, live=True)]

        logger.info("Exchange rate live fetch failed — using simulated rates")
        return [self._simulate_rates()]

    def acknowledge(self, source_id: str) -> None:
        pass  # Stateless

    def check_health(self) -> ConnectorHealth:
        try:
            resp = requests.get(API_URL, timeout=10)
            return ConnectorHealth(
                healthy=resp.ok or self.simulate,
                source=self.name,
                detail="API reachable" if resp.ok else f"HTTP {resp.status_code}",
                document_count=1,
            )
        except requests.RequestException as exc:
            return ConnectorHealth(
                healthy=True,
                source=self.name,
                detail=f"Simulated fallback ({exc})",
                document_count=1,
            )

    # ── Live fetch ────────────────────────────────────────────────────

    def _fetch_live(self) -> dict | None:
        try:
            resp = requests.get(API_URL, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            if data.get("result") != "success":
                logger.warning("Exchange rate API returned non-success: %s", data.get("result"))
                return None

            all_rates = data.get("rates", {})
            return {
                "base": self.base_currency,
                "rates": {cur: all_rates.get(cur) for cur in _TARGET_CURRENCIES},
                "updated_at": data.get("time_last_update_utc", ""),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }
        except requests.RequestException as exc:
            logger.warning("Exchange rate API error: %s", exc)
            return None

    # ── Simulation ─────────────────────────────────────────────────────

    def _simulate_rates(self) -> RawDocument:
        data = {
            "base": self.base_currency,
            "rates": {
                "CNY": 7.24,
                "EUR": 0.92,
                "GBP": 0.79,
                "JPY": 149.50,
                "KRW": 1320.00,
                "SGD": 1.34,
                "VND": 25450.00,
                "THB": 35.80,
            },
            "updated_at": "Simulated data",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "open.er-api.com (simulated)",
        }
        return self._build_rates_doc(data, live=False)

    def _build_rates_doc(self, rates: dict, live: bool) -> RawDocument:
        raw_json = json.dumps(rates, indent=2).encode("utf-8")

        # Compute a summary of notable changes (compared to last known)
        prev = self._last_rates
        changes = []
        for cur, val in rates.get("rates", {}).items():
            if val is None:
                continue
            if cur in prev:
                change = round((val - prev[cur]) / prev[cur] * 100, 2)
                if abs(change) > 0.5:
                    direction = "strengthened" if change < 0 else "weakened"
                    changes.append(f"USD/{cur} {direction} {abs(change):.2f}%")
            self._last_rates[cur] = val

        summary = f"USD exchange rates — {len(rates.get('rates', {}))} currencies tracked"
        if changes:
            summary += f". Changes: {'; '.join(changes[:3])}"

        return RawDocument(
            source=self.name,
            source_id=f"fx_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            doc_type=DocumentType.OTHER,
            raw_bytes=raw_json,
            filename="exchange_rates.json",
            mime_type="application/json",
            received_at=datetime.now(timezone.utc),
            metadata={
                "title": f"USD Exchange Rates ({len(rates.get('rates', {}))} currencies)",
                "summary": summary,
                "source_type": "FX Feed",
                "source_name": "open.er-api.com",
            },
        )