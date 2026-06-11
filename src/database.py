"""
database.py — SQLAlchemy ORM setup for the Supply Chain Compliance platform.

Defaults to a local SQLite database (supply_chain_mvp.db) for the MVP.
Set the DATABASE_URL environment variable to any SQLAlchemy-compatible
connection string (e.g. an AWS RDS Aurora PostgreSQL URI) to switch
backends without changing any model code.

Environment variables
---------------------
DATABASE_URL   (optional) Full SQLAlchemy connection string.
               Default: "sqlite:///./supply_chain_mvp.db"
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
    Session,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------

_DEFAULT_DATABASE_URL = "sqlite:///./supply_chain_mvp.db"
DATABASE_URL: str = os.getenv("DATABASE_URL", _DEFAULT_DATABASE_URL)

# connect_args is only meaningful for SQLite (enables WAL mode / threading).
_connect_args: dict = {}
if DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,          # flip to True for SQL debug output
    pool_pre_ping=True,  # verify connections before use (important for Aurora)
)


# Enable WAL mode for SQLite so concurrent readers don't block writers.
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Session:
    """
    Dependency-injection–friendly session factory.

    Usage (plain Python)::

        with get_db() as db:
            db.add(some_orm_object)
            db.commit()

    Usage (FastAPI dependency)::

        def route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM models
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Document types (enum table) ──────────────────────────────────────────


class DocumentTypeRecord(Base):
    """Lookup table for document types (EMAIL, BILL_OF_LADING, etc.)."""
    __tablename__ = "document_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(256), default="")


# ── Raw documents (ingestion source-of-truth) ────────────────────────────


class RawDocumentRecord(Base):
    """
    The original ingested document (email raw bytes, file bytes, etc.).
    Preserved for audit, re-processing, and later re-training.
    """
    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    doc_type_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("document_types.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    raw_bytes: Mapped[bytes] = mapped_column(Text)  # stored as BLOB via Text in SQLite
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # Relationships
    analysis_runs: Mapped[list["AnalysisRun"]] = relationship(
        "AnalysisRun", back_populates="raw_document", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<RawDocument id={self.id} source={self.source!r} "
            f"filename={self.filename!r}>"
        )


# ── Pipeline execution logs (structured trace) ───────────────────────────


class PipelineLog(Base):
    """
    One structured log entry per pipeline stage per run.
    Enables full traceability: what happened, when, and what data was involved.
    """
    __tablename__ = "pipeline_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    raw_doc_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("raw_documents.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)          # INGEST, VALIDATE, RULES, STORE
    status: Mapped[str] = mapped_column(String(32), nullable=False)         # STARTED, SUCCESS, FAILED, SKIPPED
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)         # free-form trace info
    snapshot_before: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # state diff / audit
    snapshot_after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Relationship back to AnalysisRun
    run: Mapped["AnalysisRun | None"] = relationship(
        "AnalysisRun", back_populates="pipeline_logs"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<PipelineLog id={self.id} run={self.run_id} stage={self.stage!r} status={self.status!r}>"


# ── Human override log ───────────────────────────────────────────────────


class HumanOverride(Base):
    """
    Records when a human operator manually overrode an automated decision.
    Critical for audit / compliance.
    """
    __tablename__ = "human_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    overridden_by: Mapped[str] = mapped_column(String(128))         # operator email / ID
    target_type: Mapped[str] = mapped_column(String(64))            # "action", "risk", "compliance_flag"
    target_id: Mapped[str] = mapped_column(String(128))             # the specific item overridden
    previous_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Relationship back to AnalysisRun
    run: Mapped["AnalysisRun | None"] = relationship(
        "AnalysisRun", back_populates="human_overrides"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


# ── Core analysis tables (existing, now linked to raw_documents) ─────────


class AnalysisRun(Base):
    """
    Primary record for one complete AI agent analysis cycle.
    All child tables hang off this via FK relationships.
    """

    __tablename__ = "analysis_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link back to the raw document that triggered this run
    raw_document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("raw_documents.id", ondelete="SET NULL"), nullable=True
    )

    # Identifiers sourced from the payload
    organization_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(512))
    ingested_at: Mapped[str] = mapped_column(String(64))

    # AI analysis metadata
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    primary_language: Mapped[str] = mapped_column(String(32))
    extracted_entities: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Pipeline bookkeeping
    pipeline_step: Mapped[str] = mapped_column(String(128))
    pipeline_status: Mapped[str] = mapped_column(String(64))
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    rules_applied: Mapped[list] = mapped_column(JSON, default=list)  # audit trail

    # Tiered confidence / escalation
    tier: Mapped[str | None] = mapped_column(String(32), nullable=True)   # AUTO, SUGGEST, ESCALATE, BLOCK
    escalation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Record metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    raw_document: Mapped[RawDocumentRecord | None] = relationship(
        "RawDocumentRecord", back_populates="analysis_runs"
    )
    compliance_flags: Mapped[list["ComplianceFlag"]] = relationship(
        "ComplianceFlag",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="select",
    )
    risks: Mapped[list["RiskRecord"]] = relationship(
        "RiskRecord",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="select",
    )
    triggered_actions: Mapped[list["TriggeredAction"]] = relationship(
        "TriggeredAction",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="select",
    )
    pipeline_logs: Mapped[list["PipelineLog"]] = relationship(
        "PipelineLog",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="select",
    )
    human_overrides: Mapped[list["HumanOverride"]] = relationship(
        "HumanOverride",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<AnalysisRun id={self.id} doc={self.document_id!r} "
            f"org={self.organization_id!r} step={self.pipeline_step!r}>"
        )


class ComplianceFlag(Base):
    """One compliance item extracted from the AI analysis."""

    __tablename__ = "compliance_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(32))
    regulatory_body: Mapped[str] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="compliance_flags")

    def __repr__(self) -> str:
        return f"<ComplianceFlag item_id={self.item_id!r} severity={self.severity!r}>"


class RiskRecord(Base):
    """One supply-chain risk extracted from the AI analysis."""

    __tablename__ = "risks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    risk_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    probability: Mapped[str] = mapped_column(String(32))
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    # Populated by rules engine when cost > $100k
    escalated_priority: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="risks")

    def __repr__(self) -> str:
        return (
            f"<RiskRecord risk_id={self.risk_id!r} cost={self.estimated_cost_usd:.2f} "
            f"priority={self.escalated_priority!r}>"
        )


class TriggeredAction(Base):
    """One automated action that was (or should be) triggered."""

    __tablename__ = "triggered_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    action_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_system: Mapped[str] = mapped_column(String(64))
    action_type: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(64))
    blocked_by_low_confidence: Mapped[bool] = mapped_column(default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="triggered_actions")

    def __repr__(self) -> str:
        return (
            f"<TriggeredAction action_id={self.action_id!r} "
            f"target={self.target_system!r} status={self.status!r}>"
        )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create all tables if they don't already exist. Safe to call on startup."""
    logger.info("Initialising database at %s", DATABASE_URL)
    Base.metadata.create_all(bind=engine)

    # Seed document types if table is empty
    _seed_document_types()

    logger.info("Database ready.")


def _seed_document_types() -> None:
    """Ensure the document_types lookup table has entries."""
    types = [
        ("EMAIL", "Email message from IMAP/mailbox"),
        ("BILL_OF_LADING", "Shipping manifest / bill of lading"),
        ("TARIFF_NOTICE", "Tariff change notification (CBP, etc.)"),
        ("PORT_UPDATE", "Port congestion / status update"),
        ("INVOICE", "Supplier invoice"),
        ("INVENTORY_REPORT", "Inventory count / stock report"),
        ("CUSTOMS_FILING", "Customs clearance filing"),
        ("CONTRACT", "Legal agreement / purchase order"),
        ("SCAN", "Scanned document (OCR needed)"),
        ("OTHER", "Uncategorised document"),
    ]
    try:
        with SessionLocal() as session:
            existing = session.query(DocumentTypeRecord).count()
            if existing == 0:
                for name, desc in types:
                    session.add(DocumentTypeRecord(name=name, description=desc))
                session.commit()
                logger.info("Seeded %d document types", len(types))
    except Exception:
        pass  # table may not exist yet on first init; safe to ignore