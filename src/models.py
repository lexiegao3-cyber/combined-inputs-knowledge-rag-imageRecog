"""
models.py — Pydantic v2 data models for the Supply Chain Compliance platform.

Validates the raw JSON string emitted by the upstream LangGraph AI agent.
"""

from __future__ import annotations

import json
import re
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Nested models
# ---------------------------------------------------------------------------


class SystemStatus(BaseModel):
    status: str
    environment: str
    pipeline_step: str
    retry_count: int = Field(ge=0)


class SourceInfo(BaseModel):
    organization_id: str
    document_id: str
    source_type: str
    filename: str
    ingested_at: str  # ISO-8601 string; keep as str for flexibility


class ExtractedEntities(BaseModel):
    carrier: str
    origin_port: str
    destination_port: str
    sku_affected: str
    estimated_delivery: str


class AIAnalysis(BaseModel):
    confidence_score: float = Field(ge=0.0, le=1.0)
    primary_language: str
    extracted_entities: ExtractedEntities


class ComplianceItem(BaseModel):
    item_id: str
    type: str
    description: str
    status: str
    severity: str
    regulatory_body: str


class Risk(BaseModel):
    risk_id: str
    category: str
    summary: str
    probability: str
    estimated_cost_usd: float = Field(ge=0.0)


class Action(BaseModel):
    action_id: str
    target_system: str
    action_type: str
    summary: str
    payload: dict[str, Any]
    status: str

    @field_validator("target_system")
    @classmethod
    def target_system_must_be_known(cls, v: str) -> str:
        """
        Soft validator — the hard rule lives in rules.py, but we normalise
        the value to uppercase here so downstream comparisons are consistent.
        """
        return v.upper()


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


class SupplyChainAnalysis(BaseModel):
    """Top-level model representing a complete AI agent analysis payload."""

    system_status: SystemStatus
    source_info: SourceInfo
    ai_analysis: AIAnalysis
    compliance_items: list[ComplianceItem] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)

    @model_validator(mode="after")
    def lists_must_not_be_empty_together(self) -> "SupplyChainAnalysis":
        """
        At least one of compliance_items, risks, or actions must be present.
        A fully empty analysis is almost certainly a malformed response.
        """
        if not self.compliance_items and not self.risks and not self.actions:
            raise ValueError(
                "Payload contains no compliance_items, risks, or actions. "
                "The AI agent likely returned an incomplete response."
            )
        return self


# ---------------------------------------------------------------------------
# Parsing helper
# ---------------------------------------------------------------------------

_MARKDOWN_FENCE_RE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def strip_markdown_fences(raw: str) -> str:
    """Remove ```json … ``` wrappers that LLMs often emit accidentally."""
    stripped = raw.strip()
    match = _MARKDOWN_FENCE_RE.match(stripped)
    return match.group(1).strip() if match else stripped


def parse_agent_output(raw_llm_string: str) -> SupplyChainAnalysis | str:
    """
    Accept the raw string from the LangGraph agent, sanitise it, and parse
    it into a validated ``SupplyChainAnalysis`` instance.

    Returns:
        SupplyChainAnalysis  — on success.
        str                  — a structured error message on failure, intended
                               to be fed back into the agent's retry loop.
    """
    if not raw_llm_string or not raw_llm_string.strip():
        return _format_parse_error("EMPTY_INPUT", "The agent returned an empty string.")

    clean = strip_markdown_fences(raw_llm_string)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as exc:
        return _format_parse_error(
            "JSON_DECODE_ERROR",
            f"Could not decode JSON from agent output. "
            f"Position {exc.pos}: {exc.msg}. "
            f"Snippet: {clean[:200]!r}",
        )

    try:
        return SupplyChainAnalysis.model_validate(data)
    except Exception as exc:  # pydantic.ValidationError or anything else
        return _format_parse_error(
            "SCHEMA_VALIDATION_ERROR",
            str(exc),
        )


def _format_parse_error(code: str, detail: str) -> str:
    """
    Return a structured error string the orchestrator can route back to the
    LangGraph agent as a retry instruction.
    """
    payload = {
        "error_code": code,
        "detail": detail,
        "instruction": (
            "Please re-generate the JSON payload strictly following the "
            "SupplyChainAnalysis schema. Do not wrap the output in markdown fences."
        ),
    }
    return json.dumps(payload, indent=2)
