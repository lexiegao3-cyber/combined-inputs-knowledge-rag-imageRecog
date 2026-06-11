"""
Ingestion Bus — manages the flow from source connectors through the pipeline.

Architecture:
  Connector.poll() → RawDocument → store in DB → run_pipeline() → record result

The bus provides:
  - Pluggable connector discovery and lifecycle
  - SQLite-backed queue (acknowledged documents are skipped)
  - Pipeline logging with before/after snapshots
  - Health checks across all connectors
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from src.connectors import (
    SourceConnector,
    RawDocument,
    ConnectorHealth,
    CONNECTOR_REGISTRY,
)
from src.database import (
    RawDocumentRecord,
    DocumentTypeRecord,
    PipelineLog,
    AnalysisRun,
    SessionLocal,
    init_db,
)
from src.pipeline import run_pipeline, PipelineResult

logger = logging.getLogger(__name__)


@dataclass
class BusHealth:
    """Aggregate health of all connectors and the bus itself."""
    healthy: bool
    connector_health: list[ConnectorHealth] = field(default_factory=list)
    total_documents: int = 0


class IngestionBus:
    """
    Main ingestion coordinator.

    Usage::

        bus = IngestionBus({
            "folder": {"path": "./demo_inputs"},
            "email": {"host": "imap.gmail.com", ...},   # optional
        })
        bus.poll_all()    # scan all connectors, process new docs
        bus.report()      # print summary
    """

    def __init__(self, connector_configs: dict[str, dict] | None = None) -> None:
        self.connectors: dict[str, SourceConnector] = {}
        connector_configs = connector_configs or {}

        for name, cfg in connector_configs.items():
            cls = CONNECTOR_REGISTRY.get(name)
            if cls is None:
                logger.warning("Unknown connector type '%s' — skipping", name)
                continue
            cfg.setdefault("name", name)
            self.connectors[name] = cls(cfg)

        logger.info("IngestionBus initialised with %d connector(s)", len(self.connectors))

    # ── Core processing ────────────────────────────────────────────────────

    def poll_all(self) -> dict[str, list[PipelineResult]]:
        """
        Poll every registered connector and process all new documents.
        
        Returns a dict mapping connector name → list of pipeline results.
        """
        results: dict[str, list[PipelineResult]] = {}
        for name, connector in self.connectors.items():
            logger.info("Polling connector '%s'...", name)
            docs = connector.poll()
            if not docs:
                logger.info("  No new documents from '%s'", name)
                results[name] = []
                continue

            logger.info("  Found %d new document(s) from '%s'", len(docs), name)
            connector_results = []
            for doc in docs:
                pipeline_result = self._process_document(doc)
                if pipeline_result.success:
                    connector.acknowledge(doc.source_id)
                connector_results.append(pipeline_result)

            results[name] = connector_results

        return results

    def _process_document(self, doc: RawDocument) -> PipelineResult:
        """Store a raw document in the DB, run the pipeline, record logs."""
        raw_doc_id = self._store_raw_document(doc)

        # Log: ingestion started
        self._log_event(
            raw_doc_id=raw_doc_id,
            stage="INGEST",
            status="SUCCESS",
            detail=f"Ingested {doc.filename} ({doc.mime_type}) from {doc.source}",
            snapshot_after={"source": doc.source, "filename": doc.filename, "doc_type": str(doc.doc_type)},
        )

        # Decode raw bytes to text for the pipeline
        try:
            text_content = doc.raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            text_content = doc.raw_bytes.decode("latin-1", errors="replace")

        # Run the pipeline
        pipeline_result = run_pipeline(text_content)

        # Store text content back to raw document record
        self._update_raw_text(raw_doc_id, text_content)

        # Log: pipeline result
        stage_status = "SUCCESS" if pipeline_result.success else "FAILED"
        self._log_event(
            raw_doc_id=raw_doc_id,
            run_id=pipeline_result.run_id,
            stage="PIPELINE",
            status=stage_status,
            detail=pipeline_result.pipeline_stage,
            snapshot_before={},
            snapshot_after={
                "success": pipeline_result.success,
                "run_id": pipeline_result.run_id,
                "stage": pipeline_result.pipeline_stage,
                "violations": len(pipeline_result.violations),
                "warnings": len(pipeline_result.warnings),
            },
        )

        return pipeline_result

    # ── Database helpers ───────────────────────────────────────────────────

    def _store_raw_document(self, doc: RawDocument) -> int:
        """Insert a raw document record and return its ID."""
        with SessionLocal() as session:
            # Resolve doc type ID
            doc_type_id = None
            if doc.doc_type:
                dt = session.query(DocumentTypeRecord).filter_by(name=doc.doc_type.value).first()
                if dt:
                    doc_type_id = dt.id

            record = RawDocumentRecord(
                source=doc.source,
                source_id=doc.source_id,
                doc_type_id=doc_type_id,
                filename=doc.filename,
                mime_type=doc.mime_type,
                raw_bytes=doc.raw_bytes,
                text_content=None,
                received_at=doc.received_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.id

    def _update_raw_text(self, raw_doc_id: int, text: str) -> None:
        """Update the text_content field after pipeline processing."""
        with SessionLocal() as session:
            record = session.query(RawDocumentRecord).filter_by(id=raw_doc_id).first()
            if record:
                record.text_content = text
                session.commit()

    def _log_event(
        self,
        raw_doc_id: int | None = None,
        run_id: int | None = None,
        stage: str = "",
        status: str = "SUCCESS",
        detail: str = "",
        snapshot_before: dict | None = None,
        snapshot_after: dict | None = None,
    ) -> None:
        """Record a structured pipeline log entry."""
        try:
            with SessionLocal() as session:
                entry = PipelineLog(
                    raw_doc_id=raw_doc_id,
                    run_id=run_id,
                    stage=stage,
                    status=status,
                    detail=detail,
                    snapshot_before=snapshot_before,
                    snapshot_after=snapshot_after,
                )
                session.add(entry)
                session.commit()
        except Exception as exc:
            logger.warning("Failed to write pipeline log: %s", exc)

    # ── Health / reporting ─────────────────────────────────────────────────

    def check_health(self) -> BusHealth:
        """Check health of all connectors."""
        connector_health: list[ConnectorHealth] = []
        total_docs = 0
        for name, connector in self.connectors.items():
            h = connector.check_health()
            connector_health.append(h)
            total_docs += h.document_count

        all_healthy = all(h.healthy for h in connector_health)
        return BusHealth(
            healthy=all_healthy,
            connector_health=connector_health,
            total_documents=total_docs,
        )

    def report(self) -> str:
        """Human-readable status report."""
        health = self.check_health()
        lines = [
            "=" * 60,
            "  Ingestion Bus — Health Report",
            "=" * 60,
            f"  System status: {'✅ HEALTHY' if health.healthy else '❌ DEGRADED'}",
            f"  Total documents available: {health.total_documents}",
        ]
        if health.connector_health:
            lines.append("")
            lines.append("  Connectors:")
            for h in health.connector_health:
                icon = "✅" if h.healthy else "❌"
                lines.append(f"    {icon} {h.source}: {h.document_count} docs | {h.detail}")
        lines.append("")
        return "\n".join(lines)