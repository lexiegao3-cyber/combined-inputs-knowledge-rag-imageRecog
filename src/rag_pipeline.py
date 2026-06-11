from __future__ import annotations

import json
from typing import Any

from src.models import parse_agent_output
from src.pipeline import PipelineResult, run_pipeline
from src.rag.agent import analyze_with_rag, repair_agent_output


def run_rag_pipeline(
    raw_text: str,
    metadata: dict[str, Any] | None = None,
    max_repairs: int = 1,
) -> PipelineResult:
    agent_json = analyze_with_rag(raw_text, metadata)

    for attempt in range(max_repairs + 1):
        agent_json = _normalize_agent_json(agent_json, metadata)
        parsed = parse_agent_output(agent_json)
        if not isinstance(parsed, (str, dict)):
            return run_pipeline(agent_json)

        if attempt >= max_repairs:
            return PipelineResult(
                success=False,
                output_data=parsed,
                pipeline_stage="RAG_VALIDATION_FAILED",
            )

        try:
            agent_json = repair_agent_output(
                raw_text=raw_text,
                invalid_json=agent_json,
                validation_error=str(parsed),
                metadata=metadata,
            )
        except Exception as exc:
            return PipelineResult(
                success=False,
                output_data={"repair_error": str(exc), "validation_error": parsed},
                pipeline_stage="RAG_REPAIR_FAILED",
            )

    return PipelineResult(
        success=False,
        output_data={"error": "Unexpected RAG validation loop exit."},
        pipeline_stage="RAG_VALIDATION_FAILED",
    )


def _normalize_agent_json(
    agent_json: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Make small-model JSON output conform to required schema shapes before
    Pydantic validation. This does not decide business meaning; it only fills
    required structural defaults that local LLMs commonly omit or set to null.
    """
    try:
        data = json.loads(agent_json)
    except json.JSONDecodeError:
        return agent_json

    if not isinstance(data, dict):
        return agent_json

    metadata = metadata or {}

    system_status = _ensure_dict(data, "system_status")
    system_status["status"] = _string_or_default(system_status.get("status"), "OK")
    system_status["environment"] = _string_or_default(
        system_status.get("environment"),
        "local_ollama_rag",
    )
    system_status["pipeline_step"] = _string_or_default(
        system_status.get("pipeline_step"),
        "POST_RAG_ANALYSIS",
    )
    system_status["retry_count"] = _int_or_default(system_status.get("retry_count"), 0)

    source_info = _ensure_dict(data, "source_info")
    source_info["organization_id"] = _string_or_default(
        source_info.get("organization_id"),
        metadata.get("organization_id", "org-greenchem-demo"),
    )
    source_info["document_id"] = _string_or_default(
        source_info.get("document_id"),
        metadata.get("document_id", "doc-rag-unknown"),
    )
    source_info["source_type"] = _string_or_default(
        source_info.get("source_type"),
        metadata.get("source_type", "RAW_DOCUMENT"),
    )
    source_info["filename"] = _string_or_default(
        source_info.get("filename"),
        metadata.get("filename", "unknown.txt"),
    )
    source_info["ingested_at"] = _string_or_default(
        source_info.get("ingested_at"),
        metadata.get("ingested_at", "Unknown"),
    )

    ai_analysis = _ensure_dict(data, "ai_analysis")
    ai_analysis["confidence_score"] = _bounded_float(
        ai_analysis.get("confidence_score"),
        default=0.5,
        minimum=0.0,
        maximum=1.0,
    )
    ai_analysis["primary_language"] = _string_or_default(
        ai_analysis.get("primary_language"),
        "en",
    )

    entities = _ensure_dict(ai_analysis, "extracted_entities")
    for key in (
        "carrier",
        "origin_port",
        "destination_port",
        "sku_affected",
        "estimated_delivery",
    ):
        entities[key] = _string_or_default(entities.get(key), "Unknown")

    compliance_items = _ensure_list(data, "compliance_items")
    risks = _ensure_list(data, "risks")
    actions = _ensure_list(data, "actions")

    if not compliance_items and not risks and not actions:
        compliance_items.append({})

    for index, item in enumerate(compliance_items):
        if not isinstance(item, dict):
            item = {}
            compliance_items[index] = item
        item["item_id"] = _string_or_default(item.get("item_id"), f"CI-RAG-{index + 1:03d}")
        item["type"] = _string_or_default(item.get("type"), "IMPORT_DOCUMENTATION")
        item["description"] = _string_or_default(
            item.get("description"),
            "Document requires supply chain compliance review.",
        )
        item["status"] = _string_or_default(item.get("status"), "FLAGGED")
        item["severity"] = _string_or_default(item.get("severity"), "MEDIUM")
        item["regulatory_body"] = _string_or_default(item.get("regulatory_body"), "US_CBP")

    for index, risk in enumerate(risks):
        if not isinstance(risk, dict):
            risk = {}
            risks[index] = risk
        risk["risk_id"] = _string_or_default(risk.get("risk_id"), f"RISK-RAG-{index + 1:03d}")
        risk["category"] = _string_or_default(risk.get("category"), "COMPLIANCE")
        risk["summary"] = _string_or_default(
            risk.get("summary"),
            "Potential supply chain compliance issue identified.",
        )
        risk["probability"] = _string_or_default(risk.get("probability"), "MEDIUM")
        risk["estimated_cost_usd"] = _bounded_float(
            risk.get("estimated_cost_usd"),
            default=0.0,
            minimum=0.0,
        )

    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            action = {}
            actions[index] = action
        action["action_id"] = _string_or_default(action.get("action_id"), f"ACT-RAG-{index + 1:03d}")
        target_system = _string_or_default(action.get("target_system"), "JIRA").upper()
        if target_system not in {"JIRA", "SLACK", "EMAIL", "SAP"}:
            target_system = "JIRA"
        action["target_system"] = target_system
        action["action_type"] = _string_or_default(action.get("action_type"), "CREATE_TICKET")
        action["summary"] = _string_or_default(
            action.get("summary"),
            "Open compliance review for extracted supply chain issue.",
        )
        payload = action.get("payload")
        action["payload"] = payload if isinstance(payload, dict) else {"priority": "Medium"}
        action["status"] = _string_or_default(action.get("status"), "PENDING")

    return json.dumps(data, indent=2)


def _ensure_dict(container: dict[str, Any], key: str) -> dict[str, Any]:
    value = container.get(key)
    if not isinstance(value, dict):
        value = {}
        container[key] = value
    return value


def _ensure_list(container: dict[str, Any], key: str) -> list[Any]:
    value = container.get(key)
    if not isinstance(value, list):
        value = []
        container[key] = value
    return value


def _string_or_default(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bounded_float(
    value: Any,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number
