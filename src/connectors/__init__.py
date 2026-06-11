"""
Source Connectors — pluggable ingestion sources for the Supply Chain Compliance platform.

Each connector implements the ``SourceConnector`` ABC and registers itself
via the ``CONNECTOR_REGISTRY``. The ingestion bus uses these to discover
and pull documents from various sources (local folder, email, live APIs).
"""

from .base import (
    SourceConnector,
    RawDocument,
    DocumentType,
    ConnectorHealth,
)
from .folder import FolderConnector
from .email import EmailConnector
from .federal_register import FederalRegisterConnector
from .shipping_rates import HARPEXConnector
from .exchange_rates import ExchangeRateConnector
from .us_china_lane import USChinaLaneConnector
from .eu_trade_lane import EUTradeLaneConnector

# All connector classes discovered by the ingestion bus
CONNECTOR_REGISTRY: dict[str, type[SourceConnector]] = {
    # Static sources
    "folder": FolderConnector,
    "email": EmailConnector,
    # Live data feeds
    "federal_register": FederalRegisterConnector,
    "harpex": HARPEXConnector,
    "exchange_rates": ExchangeRateConnector,
    "us_china_lane": USChinaLaneConnector,
    "eu_trade_lane": EUTradeLaneConnector,
}

# Default configuration for live connectors (used by --live flag)
LIVE_CONNECTOR_CONFIGS: dict[str, dict] = {
    "federal_register": {
        "name": "federal-register",
        "days_back": 7,
    },
    "harpex": {
        "name": "harpex",
        "simulate": True,  # Start with simulation until live API confirmed
    },
    "exchange_rates": {
        "name": "exchange-rates",
        "simulate": False,
    },
    "us_china_lane": {
        "name": "us-china-lane",
        "simulate": True,
    },
    "eu_trade_lane": {
        "name": "eu-trade-lane",
        "simulate": True,
    },
}

__all__ = [
    "SourceConnector",
    "RawDocument",
    "DocumentType",
    "ConnectorHealth",
    "FolderConnector",
    "EmailConnector",
    "FederalRegisterConnector",
    "HARPEXConnector",
    "ExchangeRateConnector",
    "USChinaLaneConnector",
    "EUTradeLaneConnector",
    "CONNECTOR_REGISTRY",
    "LIVE_CONNECTOR_CONFIGS",
]