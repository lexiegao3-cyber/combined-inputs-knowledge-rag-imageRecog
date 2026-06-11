"""
pipeline.py — Orchestration layer for the Supply Chain Compliance platform.

Execution flow
--------------
  raw LLM string
      │
      ▼
  [Validation]  models.parse_agent_output()
      │  failure → return structured error dictionary to agent retry loop
      ▼
  [Rules Engine]  rules.run_rules()
      │  violations? → log & optionally halt automated actions
      ▼
  [Database Save]  save_analysis_run()
      │
      ▼
  PipelineResult
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from contextlib import contextmanager
from typing import Generator, Any

from sqlalchemy.orm import Session

from src import models as m
from src import rules as r
from src.database import (
    AnalysisRun,
    ComplianceFlag,
    RiskRecord,
    TriggeredAction,
    SessionLocal,
    init_db,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("pipeline")


# ---------------------------------------------------------------------------
# Pipeline result container
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Outcome of one complete pipeline run."""

    success: bool
    run_id: int | None = None
    # Swapped from str to Any to natively support structural error dictionaries 
    output_data: Any | None = None  
    pipeline_stage: str = "INITIALIZED"
    violations: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied_rules: list[str] = field(default_factory=list)

    # New fields from the YAML rules engine
    rule_result: r.RuleResult | None = None

    def summary(self) -> str:
        lines = [
            f"Pipeline {'SUCCESS' if self.success else 'FAILURE'}",
            f"  run_id         : {self.run_id}",
            f"  stage          : {self.pipeline_stage}",
            f"  violations     : {len(self.violations)}",
            f"  warnings       : {len(self.warnings)}",
            f"  rules applied  : {len(self.applied_rules)}",
        ]
        if self.violations:
            lines.append("  ---- VIOLATIONS ----")
            for v in self.violations:
                lines.append(f"    • {v}")
        if self.warnings:
            lines.append("  ---- WARNINGS ------")
            for w in self.warnings:
                lines.append(f"    ⚠ {w}")
        lines.append("  ---- RULES ---------")
        for rule in self.applied_rules:
            lines.append(f"    ✓ {rule}")
        return "\n".join(lines)

    def to_dashboard_json(self) -> dict[str, Any]:
        """
        Transforms pipeline output into the JSON format expected by
        Jake's frontend dashboard (see frontend/js/sections/riskActionsData.js).
        """
        if not self.success or not isinstance(self.output_data, dict):
            return {
                "routing_status": {
                    "pipeline_stage": self.pipeline_stage,
                    "is_valid": False,
                    "error_summary": self.output_data,
                }
            }

        output = self.output_data
        source_info = output.get("source_info", {})
        ai_analysis = output.get("ai_analysis", {})
        entities = ai_analysis.get("extracted_entities", {})
        system_status = output.get("system_status", {})

        # ── Build risks matching Jake's RISKS format ────────────────────
        risks_list = output.get("risks", [])
        compliance_items = output.get("compliance_items", [])

        risks = []
        for i, risk in enumerate(risks_list):
            risk_id = f"risk_{i + 1:03d}"
            cost = float(risk.get("estimated_cost_usd", 0))
            level = "High" if cost > 100000 else ("Medium" if cost > 10000 else "Low")
            probability = risk.get("probability", "MEDIUM")
            if probability == "HIGH":
                level = "High" if level != "High" else level  # keep High

            # Determine evidence confidence (0-100 scale)
            conf_pct = int(ai_analysis.get("confidence_score", 0.0) * 100)

            risks.append({
                "id": risk_id,
                "title": risk.get("summary", "Risk")[:80],
                "category": risk.get("category", "Other"),
                "level": level,
                "summary": risk.get("summary", ""),
                "evidence": {
                    "sourceType": source_info.get("source_type", "AI Analysis"),
                    "sourceName": f"AI Agent — {source_info.get('document_id', 'unknown')}",
                    "sourceDate": source_info.get("ingested_at", ""),
                    "sourceCategory": risk.get("category", "Other"),
                    "extractedFact": entities.get("sku_affected", "") + " — " + risk.get("summary", "")[:120],
                    "confidence": min(conf_pct, 100),
                    "validationStatus": "Rule check passed",
                    "humanReview": "Required" if cost > 100000 else "Not required",
                },
            })

        # ── Build actions matching Jake's ACTIONS format ────────────────
        actions_list = output.get("actions", [])

        # Compute a Human Review Required flag from the rules engine
        has_human_review = False
        if self.rule_result and self.rule_result.tier in ("SUGGEST", "ESCALATE", "BLOCK"):
            has_human_review = True

        actions = []
        for i, action in enumerate(actions_list):
            act_id = f"act_{i + 1:03d}"
            related_risk = risks[i % len(risks)]["id"] if risks else "risk_001"
            priority = action.get("payload", {}).get("priority", "Medium")
            level = priority if priority in ("High", "Medium", "Low") else "Medium"

            # Determine approval state from pipeline tier
            if has_human_review and level == "High":
                approval = "Human review required"
            elif has_human_review:
                approval = "Finance sign-off required"
            else:
                approval = "No approval required"

            department = "Operations"
            target = action.get("target_system", "GENERIC")
            if target == "SAP":
                department = "Supply Chain"
            elif target == "SLACK":
                department = "Logistics"
            elif target == "JIRA":
                department = "Procurement"
            elif target == "EMAIL":
                department = "Finance"

            actions.append({
                "id": act_id,
                "action": action.get("summary", "Automated action"),
                "relatedRiskId": related_risk,
                "department": department,
                "owner": "AI Assistant",
                "priority": level,
                "due": entities.get("estimated_delivery", "48 hours"),
                "status": action.get("status", "Open"),
                "approvalState": approval,
                "why": f"Triggered by {target} — {action.get('summary', '')[:100]}",
            })

        # ── Assemble dashboard payload ──────────────────────────────────
        total_exposure = sum(float(r.get("estimated_cost_usd", 0)) for r in risks_list)

        return {
            "summary": {
                "run_id": self.run_id,
                "organization_id": source_info.get("organization_id"),
                "document_id": source_info.get("document_id"),
                "filename": source_info.get("filename"),
                "source_type": source_info.get("source_type"),
                "ingested_at": source_info.get("ingested_at"),
                "confidence_score": ai_analysis.get("confidence_score"),
                "primary_language": ai_analysis.get("primary_language"),
                "tier": system_status.get("pipeline_step", "UNKNOWN"),
                "total_estimated_exposure_usd": total_exposure,
            },
            "routing_status": {
                "pipeline_stage": self.pipeline_stage,
                "is_valid": len(self.violations) == 0,
                "blocked_actions": system_status.get("pipeline_step", "").startswith("TIER_"),
                "applied_rules": self.applied_rules,
                "violations": self.violations,
                "warnings": self.warnings,
            },
            "extracted_entities": entities,
            "compliance_flags": [
                {
                    "id": f"flag_{i+1:03d}",
                    "item_id": item.get("item_id", ""),
                    "type": item.get("type", ""),
                    "description": item.get("description", ""),
                    "status": item.get("status", "FLAGGED"),
                    "severity": item.get("severity", "MEDIUM"),
                    "regulatory_body": item.get("regulatory_body", ""),
                }
                for i, item in enumerate(compliance_items)
            ],
            "risks": risks,
            "actions": actions,
        }


# ---------------------------------------------------------------------------
# Session helper
# ---------------------------------------------------------------------------


@contextmanager
def _get_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session with automatic commit/rollback."""
    db: Session = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Database persistence
# ---------------------------------------------------------------------------


def save_analysis_run(
    analysis: m.SupplyChainAnalysis,
    rule_result: r.RuleResult,
    db: Session,
) -> AnalysisRun:
    """
    Persist the validated, rule-processed analysis to the database.
    """
    # Safeguard against missing rule engine fields
    applied_rules = getattr(rule_result, "applied_rules", [])

    run = AnalysisRun(
        organization_id=analysis.source_info.organization_id,
        document_id=analysis.source_info.document_id,
        source_type=analysis.source_info.source_type,
        filename=analysis.source_info.filename,
        ingested_at=analysis.source_info.ingested_at,
        confidence_score=analysis.ai_analysis.confidence_score,
        primary_language=analysis.ai_analysis.primary_language,
        extracted_entities=analysis.ai_analysis.extracted_entities.model_dump(),
        pipeline_step=analysis.system_status.pipeline_step,
        pipeline_status=analysis.system_status.status,
        retry_count=analysis.system_status.retry_count,
        rules_applied=applied_rules,
    )
    db.add(run)
    db.flush()  

    # Compliance flags
    for item in analysis.compliance_items:
        db.add(
            ComplianceFlag(
                run_id=run.id,
                item_id=item.item_id,
                type=item.type,
                description=item.description,
                status=item.status,
                severity=item.severity,
                regulatory_body=item.regulatory_body,
            )
        )

    # Risks 
    for risk in analysis.risks:
        db.add(
            RiskRecord(
                run_id=run.id,
                risk_id=risk.risk_id,
                category=risk.category,
                summary=risk.summary,
                probability=risk.probability,
                estimated_cost_usd=risk.estimated_cost_usd,
            )
        )

    # Actions
    for action in analysis.actions:
        db.add(
            TriggeredAction(
                run_id=run.id,
                action_id=action.action_id,
                target_system=action.target_system,
                action_type=action.action_type,
                summary=action.summary,
                payload=action.payload,
                status=action.status,
            )
        )

    logger.info(
        "Saved AnalysisRun id=%d  flags=%d  risks=%d  actions=%d",
        run.id,
        len(analysis.compliance_items),
        len(analysis.risks),
        len(analysis.actions),
    )
    return run


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def run_pipeline(raw_llm_string: str) -> PipelineResult:
    """
    Execute the full Validation → Rules → Database pipeline.
    """
    # ── Step 1: Validate ────────────────────────────────────────────────────
    logger.info("Step 1/3 — Validation")
    parsed = m.parse_agent_output(raw_llm_string)

    # Check for string/dict return format coming from models.py parsing failures
    if isinstance(parsed, str) or isinstance(parsed, dict):
        logger.error("Validation failed. Returning error metadata to agent retry loop.")
        return PipelineResult(
            success=False, 
            output_data=parsed, 
            pipeline_stage="VALIDATION_FAILED"
        )

    analysis: m.SupplyChainAnalysis = parsed
    logger.info(
        "Validation passed. doc_id=%s  org=%s  confidence=%.3f",
        analysis.source_info.document_id,
        analysis.source_info.organization_id,
        analysis.ai_analysis.confidence_score,
    )

    # ── Step 2: Rules ───────────────────────────────────────────────────────
    logger.info("Step 2/3 — Rules Engine")
    
    # Use the new YAML-driven rules engine
    if hasattr(r, "run_rules"):
        rule_result = r.run_rules(analysis)
    elif hasattr(r, "evaluate_business_rules"):
        rule_result = r.evaluate_business_rules(analysis)
    else:
        raise AttributeError("No valid rule evaluation function found inside rules.py")

    # Guard against variable naming properties on RuleResult objects
    is_valid = getattr(rule_result, "is_valid", True)
    violations = getattr(rule_result, "violations", [])
    applied_rules = getattr(rule_result, "applied_rules", [])
    warnings = getattr(rule_result, "warnings", [])

    if not is_valid or len(violations) > 0:
        logger.warning(
            "Rules engine found %d violation(s). Automated actions are managed accordingly.",
            len(violations),
        )

    # ── Step 3: Database Save ───────────────────────────────────────────────
    logger.info("Step 3/3 — Database Save")
    try:
        with _get_session() as db:
            run_orm = save_analysis_run(analysis, rule_result, db)
            run_id = run_orm.id
    except Exception as exc:
        logger.exception("Database save failed.")
        return PipelineResult(
            success=False,
            output_data={"database_error": str(exc)},
            pipeline_stage="DATABASE_WRITE_CRASH",
            violations=violations,
            warnings=warnings,
            applied_rules=applied_rules,
        )

    result = PipelineResult(
        success=True,
        run_id=run_id,
        output_data=analysis.model_dump(),
        pipeline_stage="SUCCESSFULLY_STORED",
        violations=violations,
        warnings=warnings,
        applied_rules=applied_rules,
        rule_result=rule_result,
    )
    return result


# ---------------------------------------------------------------------------
# Mock execution example
# ---------------------------------------------------------------------------

_MOCK_AGENT_OUTPUT = """
```json
{
  "system_status": {
    "status": "OK",
    "environment": "local_mvp",
    "pipeline_step": "POST_AI_ANALYSIS",
    "retry_count": 0
  },
  "source_info": {
    "organization_id": "org-acme-001",
    "document_id": "doc-2024-shipment-7821",
    "source_type": "BILL_OF_LADING",
    "filename": "bol_7821_jun2024.pdf",
    "ingested_at": "2024-06-15T08:32:00Z"
  },
  "ai_analysis": {
    "confidence_score": 0.87,
    "primary_language": "en",
    "extracted_entities": {
      "carrier": "Maersk Line",
      "origin_port": "Shanghai (CNSHA)",
      "destination_port": "Los Angeles (USLAX)",
      "sku_affected": "SKU-EL-4892",
      "estimated_delivery": "2024-07-08"
    }
  },
  "compliance_items": [
    {
      "item_id": "CI-001",
      "type": "TARIFF_CLASSIFICATION",
      "description": "HS code 8542.31 may be subject to Section 301 tariffs.",
      "status": "FLAGGED",
      "severity": "HIGH",
      "regulatory_body": "US_CBP"
    },
    {
      "item_id": "CI-002",
      "type": "COUNTRY_OF_ORIGIN",
      "description": "Country-of-origin certificate missing from shipment docs.",
      "status": "MISSING",
      "severity": "MEDIUM",
      "regulatory_body": "US_CBP"
    }
  ],
  "risks": [
    {
      "risk_id": "RISK-001",
      "category": "FINANCIAL",
      "summary": "Potential additional tariff duty of $145,000 if HS code reclassified.",
      "probability": "MEDIUM",
      "estimated_cost_usd": 145000.00
    },
    {
      "risk_id": "RISK-002",
      "category": "DELAY",
      "summary": "CBP hold likely if COO certificate not provided within 48h.",
      "probability": "HIGH",
      "estimated_cost_usd": 18500.00
    }
  ],
  "actions": [
    {
      "action_id": "ACT-RISK-001-JIRA",
      "target_system": "JIRA",
      "action_type": "CREATE_TICKET",
      "summary": "Open compliance review ticket for HS code reclassification risk.",
      "payload": {"project": "COMPLIANCE", "priority": "High", "risk_id": "RISK-001"},
      "status": "PENDING"
    },
    {
      "action_id": "ACT-RISK-002-SLACK",
      "target_system": "SLACK",
      "action_type": "SEND_ALERT",
      "summary": "Alert logistics team about missing COO certificate.",
      "payload": {"channel": "#logistics-alerts", "mention": "@logistics-lead"},
      "status": "PENDING"
    },
    {
      "action_id": "ACT-RISK-001-SAP",
      "target_system": "SAP",
      "action_type": "UPDATE_RECORD",
      "summary": "Flag shipment record in SAP for compliance hold.",
      "payload": {"shipment_id": "SHP-7821", "flag": "COMPLIANCE_HOLD"},
      "status": "PENDING"
    }
  ]
}
```
"""

if __name__ == "__main__":
    print("=" * 70)
    print("  Supply Chain Compliance Pipeline — MVP Demonstration")
    print("=" * 70)
    init_db()
    result = run_pipeline(_MOCK_AGENT_OUTPUT)

    print()
    print(result.summary())
    print()
    print("=== Dashboard JSON ===")
    print(json.dumps(result.to_dashboard_json(), indent=2))