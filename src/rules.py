"""
rules.py — Data-driven Rules Engine v2 for the Supply Chain Compliance platform.

Rules are defined in ``rules_config.yaml`` (or any path via ``RULES_CONFIG`` env var)
in a declarative format. Each rule specifies:
  - trigger conditions (field path, operator, threshold)
  - actions (mutations, notifications, violations)
  - jurisdiction scoping
  - optional DAG dependencies

Key features over v1:
  - No Python code changes needed to add/edit rules
  - Jurisdiction-aware (US, EU, UK, SEA regulatory frameworks)
  - DAG-based execution (rules can depend on other rules)
  - Structured audit trail with before/after snapshots
  - Tiered confidence / human escalation built in
"""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from pathlib import Path

import yaml

from src.models import (
    Action,
    ComplianceItem,
    Risk,
    SupplyChainAnalysis,
    ExtractedEntities,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RULES_CONFIG_PATH = os.getenv("RULES_CONFIG", "rules_config.yaml")

# Confidence tier thresholds
CONFIDENCE_TIERS: list[tuple[float, str, str]] = [
    (0.90, "AUTO", "Full auto-execute — all actions fire."),
    (0.70, "SUGGEST", "Execute low-risk actions only; flag for review."),
    (0.50, "ESCALATE", "Escalate to human; suggest actions only."),
    (0.00, "BLOCK", "Block all actions; notify senior compliance officer."),
]

# Available operator implementations
_OPERATORS: dict[str, Callable] = {}


# ---------------------------------------------------------------------------
# Data models for the rule definition
# ---------------------------------------------------------------------------


@dataclass
class RuleTrigger:
    """The condition that fires a rule."""
    field: str                              # JSONPath-like field reference
    operator: str                           # >, <, >=, <=, ==, !=, in, not_in, exists, regex, within_hours
    value: Any = None                       # threshold to compare against (None for exists operator)


@dataclass
class RuleAction:
    """One action to take when a rule triggers."""
    type: str                               # set_field, mutate_payload, block_actions, violation, notify, warn, add_compliance_flag
    target: str | None = None               # field path to modify
    value: Any | None = None                # value to set (for set_field)
    set: dict | None = None                 # key/value pairs to merge (for mutate_payload)
    message: str | None = None              # for violation / warn / notify
    channel: str | None = None              # slack, email
    recipient: str | None = None            # channel name or email address
    reason: str | None = None               # for block_actions
    # For add_compliance_flag
    type_: str | None = None                # rename to avoid shadowing
    severity: str | None = None
    description: str | None = None
    regulatory_body: str | None = None


@dataclass
class RuleDef:
    """Complete definition of one business rule loaded from YAML."""
    id: str
    name: str
    description: str
    jurisdictions: list[str]
    severity: str
    trigger: RuleTrigger
    actions: list[RuleAction]
    depends_on: list[str]


# ---------------------------------------------------------------------------
# Rule evaluation result
# ---------------------------------------------------------------------------


@dataclass
class RuleResult:
    """Outcome of running the full rules engine against one payload."""

    analysis: SupplyChainAnalysis
    """The (possibly mutated) analysis object after all rules ran."""

    applied_rules: list[str] = field(default_factory=list)
    """Human-readable audit trail of every rule that fired."""

    violations: list[str] = field(default_factory=list)
    """Hard violations — items that must be fixed before the pipeline continues."""

    warnings: list[str] = field(default_factory=list)
    """Soft issues logged for visibility but not blocking."""

    # Enhanced audit trail
    evaluation_trace: list[dict] = field(default_factory=list)
    """Detailed trace of each rule evaluation (what matched, what changed)."""

    snapshot_before: dict | None = None
    """JSON snapshot of the analysis BEFORE rules ran."""

    snapshot_after: dict | None = None
    """JSON snapshot of the analysis AFTER rules ran."""

    # Tiered confidence
    tier: str = "AUTO"
    """Computed confidence tier for this run."""

    tier_reason: str = ""
    """Why this tier was assigned."""

    blocked_actions: list[str] = field(default_factory=list)
    """IDs of actions that were blocked."""

    @property
    def is_valid(self) -> bool:
        """False if any hard violations were found."""
        return len(self.violations) == 0


# ---------------------------------------------------------------------------
# Operator registry
# ---------------------------------------------------------------------------


def _register_op(name: str) -> Callable:
    """Decorator to register an operator function."""
    def wrapper(fn: Callable) -> Callable:
        _OPERATORS[name] = fn
        return fn
    return wrapper


def _resolve_field(data: dict, field_path: str) -> Any:
    """
    Simple JSONPath-like field resolver.
    Supports:
      - simple: "ai_analysis.confidence_score"
      - array iteration: "risks[].estimated_cost_usd"
      - filtered: "risks[?category == 'DELAY'].estimated_cost_usd"
      - chained: "actions[?contains(action_id, risk.risk_id)].payload"
    """
    # Handle template variables in the path itself (like risk.risk_id)
    # This is called per-match, so the template is already resolved

    parts = field_path.split(".", 1)
    key = parts[0]

    # Check for filtered array access: risks[?category == 'DELAY']
    filter_match = re.match(r"^(\w+)\[([^]]+)\]$", key)
    if filter_match:
        array_name = filter_match.group(1)
        filter_expr = filter_match.group(2)
        arr = data.get(array_name, [])
        if not isinstance(arr, list):
            return []
        return _apply_filter(arr, filter_expr, parts[1] if len(parts) > 1 else None)

    # Check for simple array access: risks[]
    array_match = re.match(r"^(\w+)\[\]$", key)
    if array_match:
        array_name = array_match.group(1)
        arr = data.get(array_name, [])
        if not isinstance(arr, list):
            return []
        if len(parts) > 1:
            results = []
            for item in arr:
                if isinstance(item, dict):
                    val = _resolve_field(item, parts[1])
                    if isinstance(val, list):
                        results.extend(val)
                    else:
                        results.append(val)
            return results
        return arr

    # Simple field access
    val = data.get(key) if isinstance(data, dict) else None
    if val is None:
        return None
    if len(parts) > 1 and isinstance(val, dict):
        return _resolve_field(val, parts[1])
    return val


def _apply_filter(arr: list, filter_expr: str, sub_path: str | None) -> list:
    """
    Apply a filter expression like "?category == 'DELAY'" to a list of dicts.
    Only supports simple conditions for now: field == value, field != value, or compound with &&
    """
    # Handle compound: ?probability == 'HIGH' && estimated_cost_usd > 50000
    compound_match = re.match(r"\?(\w+)\s*(==|!=|>|<|>=|<=)\s*'([^']+)'\s*&&\s*(\w+)\s*(==|!=|>|<|>=|<=)\s*(\d+)", filter_expr)
    if compound_match:
        field1, op1, val1, field2, op2, val2_str = compound_match.groups()
        val2 = float(val2_str)
        results = []
        for item in arr:
            if not isinstance(item, dict):
                continue
            f1 = str(item.get(field1, ""))
            f2 = item.get(field2)
            if _compare(f1, op1, val1) and _compare(f2, op2, val2):
                if sub_path:
                    val = _resolve_field(item, sub_path)
                    results.append(val)
                else:
                    results.append(item)
        return results

    # Simple filter: ?field == 'value'
    simple_match = re.match(r"\?(\w+)\s*(==|!=|>|<|>=|<=|in)\s*'([^']+)'", filter_expr)
    if not simple_match:
        return arr

    field, op, value = simple_match.groups()
    results = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        item_val = item.get(field)
        if _compare(item_val, op, value):
            if sub_path:
                val = _resolve_field(item, sub_path)
                results.append(val)
            else:
                results.append(item)
    return results


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """Compare two values with the given operator."""
    try:
        if operator == "==":
            return str(actual) == str(expected)
        elif operator == "!=":
            return str(actual) != str(expected)
        elif operator in (">", "<", ">=", "<="):
            return _numeric_compare(float(actual), operator, float(expected))
        elif operator == "in":
            if isinstance(expected, str):
                return expected in str(actual)
            return actual in expected
    except (ValueError, TypeError):
        return False
    return False


def _numeric_compare(actual: float, operator: str, expected: float) -> bool:
    if operator == ">":
        return actual > expected
    elif operator == "<":
        return actual < expected
    elif operator == ">=":
        return actual >= expected
    elif operator == "<=":
        return actual <= expected
    return False


@_register_op(">")
def _op_gt(field_val: list | Any, threshold: Any) -> list[tuple[Any, dict]]:
    """Field values > threshold. Returns list of (value, context_dict) tuples."""
    results = []
    for val, ctx in _iter_field_values(field_val):
        try:
            if float(val) > float(threshold):
                results.append((val, ctx))
        except (ValueError, TypeError):
            pass
    return results


@_register_op("<")
def _op_lt(field_val: list | Any, threshold: Any) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        try:
            if float(val) < float(threshold):
                results.append((val, ctx))
        except (ValueError, TypeError):
            pass
    return results


@_register_op(">=")
def _op_ge(field_val: list | Any, threshold: Any) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        try:
            if float(val) >= float(threshold):
                results.append((val, ctx))
        except (ValueError, TypeError):
            pass
    return results


@_register_op("<=")
def _op_le(field_val: list | Any, threshold: Any) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        try:
            if float(val) <= float(threshold):
                results.append((val, ctx))
        except (ValueError, TypeError):
            pass
    return results


@_register_op("==")
def _op_eq(field_val: list | Any, threshold: Any) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        if str(val) == str(threshold):
            results.append((val, ctx))
    return results


@_register_op("!=")
def _op_neq(field_val: list | Any, threshold: Any) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        if str(val) != str(threshold):
            results.append((val, ctx))
    return results


@_register_op("in")
def _op_in(field_val: list | Any, threshold: list) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        if str(val) in [str(t) for t in (threshold or [])]:
            results.append((val, ctx))
    return results


@_register_op("not_in")
def _op_not_in(field_val: list | Any, threshold: list) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        if str(val) not in [str(t) for t in (threshold or [])]:
            results.append((val, ctx))
    return results


@_register_op("exists")
def _op_exists(field_val: list | Any, threshold: Any = None) -> list[tuple[Any, dict]]:
    """Check if filtered results exist (non-empty list)."""
    results = _iter_field_values(field_val)
    return results if results else []


@_register_op("regex")
def _op_regex(field_val: list | Any, pattern: str) -> list[tuple[Any, dict]]:
    results = []
    for val, ctx in _iter_field_values(field_val):
        if re.search(pattern, str(val)):
            results.append((val, ctx))
    return results


@_register_op("within_hours")
def _op_within_hours(field_val: list | Any, hours: int) -> list[tuple[Any, dict]]:
    """Check if an estimated_delivery date is within N hours from now."""
    from datetime import datetime, timezone, timedelta
    results = []
    now = datetime.now(timezone.utc)
    for val, ctx in _iter_field_values(field_val):
        try:
            dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            if now <= dt <= now + timedelta(hours=int(hours)):
                results.append((val, ctx))
        except (ValueError, TypeError):
            pass
    return results


def _iter_field_values(field_val: Any) -> list[tuple[Any, dict]]:
    """
    Convert a resolved field value into a list of (value, context) tuples.
    Each context dict carries the parent objects for template resolution.
    """
    if field_val is None:
        return []
    if isinstance(field_val, list):
        return [(v, {}) for v in field_val]
    if isinstance(field_val, dict):
        # This is a single object, extract all leaf values
        return [(v, {}) for v in field_val.values() if not isinstance(v, (dict, list))]
    return [(field_val, {})]


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------


def load_rules_config(path: str | None = None) -> list[RuleDef]:
    """Load rule definitions from a YAML file."""
    config_path = path or RULES_CONFIG_PATH
    logger.info("Loading rules config from %s", config_path)

    if not os.path.exists(config_path):
        logger.warning("Rules config %s not found — using built-in defaults", config_path)
        return _builtin_defaults()

    with open(config_path, "r") as f:
        data = yaml.safe_load(f)

    rules: list[RuleDef] = []
    for entry in data.get("rules", []):
        t = entry["trigger"]
        actions = []
        for a in entry.get("actions", []):
            actions.append(RuleAction(
                type=a["type"],
                target=a.get("target"),
                value=a.get("value"),
                set=a.get("set"),
                message=a.get("message"),
                channel=a.get("channel"),
                recipient=a.get("recipient"),
                reason=a.get("reason"),
                type_=a.get("flag_type"),
                severity=a.get("severity"),
                description=a.get("description"),
                regulatory_body=a.get("regulatory_body"),
            ))
        rules.append(RuleDef(
            id=entry["id"],
            name=entry["name"],
            description=entry.get("description", ""),
            jurisdictions=entry.get("jurisdictions", ["US", "EU"]),
            severity=entry.get("severity", "MEDIUM"),
            trigger=RuleTrigger(
                field=t["field"],
                operator=t["operator"],
                value=t.get("value"),
            ),
            actions=actions,
            depends_on=entry.get("depends_on", []),
        ))

    logger.info("Loaded %d rules from config", len(rules))
    return rules


def _builtin_defaults() -> list[RuleDef]:
    """Fallback rules if no YAML config is found."""
    return [
        RuleDef(
            id="financial_limit",
            name="Financial Risk Escalation",
            description="Escalate actions for risks > $100k",
            jurisdictions=["US", "EU", "UK", "SEA"],
            severity="HIGH",
            trigger=RuleTrigger(field="risks[].estimated_cost_usd", operator=">", value=100000),
            actions=[RuleAction(type="warn", message="Financial limit exceeded")],
            depends_on=[],
        ),
    ]


# ---------------------------------------------------------------------------
# Main rules engine
# ---------------------------------------------------------------------------


def _compute_tier(confidence: float) -> tuple[str, str]:
    """Map a confidence score to a tier."""
    for threshold, tier, reason in CONFIDENCE_TIERS:
        if confidence >= threshold:
            return tier, reason
    return "BLOCK", "Confidence score below all thresholds."


def _resolve_template(template: str, context: dict) -> str:
    """Resolve {{variables}} in a template string using context dict."""
    def _replace(match: re.Match) -> str:
        expr = match.group(1).strip()
        # Support format specifiers like :,.2f
        if ":" in expr:
            var_path, fmt = expr.split(":", 1)
        else:
            var_path, fmt = expr, ""

        val = context
        for part in var_path.split("."):
            if isinstance(val, dict):
                val = val.get(part, "")
            elif isinstance(val, (list, tuple)):
                try:
                    idx = int(part)
                    val = val[idx]
                except (ValueError, IndexError):
                    val = ""
            else:
                val = ""
        return str(val)
    return re.sub(r"\{\{(.*?)\}\}", _replace, template)


def _get_context_for_match(rule_id: str, matched_item: Any, analysis_dict: dict) -> dict:
    """Build a template context dict from a matched item and the full analysis."""
    ctx = {"analysis": analysis_dict}
    if isinstance(matched_item, tuple) and len(matched_item) >= 1:
        ctx["risk"] = {"risk_id": str(matched_item[0])}
    return ctx


def evaluate_rule(
    rule: RuleDef,
    analysis_dict: dict,
    analysis: SupplyChainAnalysis,
    result: RuleResult,
    jurisdiction: str | None = None,
) -> bool:
    """
    Evaluate one rule against the analysis.
    Returns True if the rule triggered (matched), False otherwise.
    """
    jurs = rule.jurisdictions
    if jurisdiction and jurisdiction not in jurs:
        return False  # rule not applicable to this jurisdiction

    # Resolve the trigger field
    field_val = _resolve_field(analysis_dict, rule.trigger.field)

    # Execute the operator
    op_fn = _OPERATORS.get(rule.trigger.operator)
    if op_fn is None:
        logger.warning("Rule %s: unknown operator '%s'", rule.id, rule.trigger.operator)
        return False

    matches = op_fn(field_val, rule.trigger.value)

    # Triggered if there are matches
    if not matches:
        return False

    logger.info("Rule '%s' [%s] triggered — %d match(es)", rule.id, rule.severity, len(matches))

    # Execute actions
    for match_val, ctx in matches:
        action_ctx = {"analysis": analysis_dict, "risk": {}, "item": {}, "action": {}}
        # Populate context from the matched value
        if isinstance(match_val, dict):
            action_ctx.update(match_val)
        elif isinstance(match_val, (int, float, str)):
            action_ctx["value"] = match_val

        for action_def in rule.actions:
            _execute_action(action_def, analysis, result, action_ctx)

    # Record audit trail
    trace_entry = {
        "rule_id": rule.id,
        "rule_name": rule.name,
        "severity": rule.severity,
        "matches": len(matches),
        "matched_values": [str(m[0])[:100] for m in matches[:5]],
    }
    result.evaluation_trace.append(trace_entry)

    rule_entry = f"Rule {len(result.applied_rules) + 1} [{rule.id}]: {rule.name}"
    result.applied_rules.append(rule_entry)

    return True


def _execute_action(
    action_def: RuleAction,
    analysis: SupplyChainAnalysis,
    result: RuleResult,
    context: dict,
) -> None:
    """Execute a single rule action."""
    try:
        if action_def.type == "set_field":
            _action_set_field(action_def, analysis, context)
        elif action_def.type == "mutate_payload":
            _action_mutate_payload(action_def, analysis, context)
        elif action_def.type == "block_actions":
            _action_block_actions(action_def, analysis, result, context)
        elif action_def.type == "violation":
            msg = _resolve_template(action_def.message or "", context)
            result.violations.append(msg)
        elif action_def.type == "warn":
            msg = _resolve_template(action_def.message or "", context)
            result.warnings.append(msg)
        elif action_def.type == "add_compliance_flag":
            _action_add_flag(action_def, analysis, context)
        elif action_def.type == "notify":
            # For MVP, just log the notification. Real impl sends Slack/email.
            msg = _resolve_template(action_def.message or "", context)
            logger.info(
                "NOTIFY channel=%s recipient=%s message=%s",
                action_def.channel, action_def.recipient, msg,
            )
    except Exception as exc:
        logger.warning("Action '%s' failed: %s", action_def.type, exc)


def _action_set_field(
    action: RuleAction,
    analysis: SupplyChainAnalysis,
    context: dict,
) -> None:
    """Set a field on the analysis object using dotted path."""
    if not action.target:
        return
    parts = action.target.split(".")
    obj = analysis
    for part in parts[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return
    setattr(obj, parts[-1], action.value)


def _action_mutate_payload(
    action: RuleAction,
    analysis: SupplyChainAnalysis,
    context: dict,
) -> None:
    """Merge key/value pairs into action payloads."""
    if not action.target or not action.set:
        return
    # Target format: "actions[].payload" — iterate all actions
    for a in analysis.actions:
        for key, value in action.set.items():
            a.payload[key] = value


def _action_block_actions(
    action: RuleAction,
    analysis: SupplyChainAnalysis,
    result: RuleResult,
    context: dict,
) -> None:
    """Block all actions by setting status to BLOCKED."""
    for a in analysis.actions:
        a.status = "BLOCKED_LOW_CONFIDENCE"
        result.blocked_actions.append(a.action_id)


def _action_add_flag(
    action: RuleAction,
    analysis: SupplyChainAnalysis,
    context: dict,
) -> None:
    """Add a compliance flag to the analysis."""
    flag = ComplianceItem(
        item_id=f"auto-{action.type_ or 'FLAG'}-{len(analysis.compliance_items) + 1}",
        type=action.type_ or "AUTO_FLAG",
        description=action.description or "",
        status="FLAGGED",
        severity=action.severity or "MEDIUM",
        regulatory_body=action.regulatory_body or "INTERNAL",
    )
    analysis.compliance_items.append(flag)


# ---------------------------------------------------------------------------
# DAG execution planner
# ---------------------------------------------------------------------------


def _topological_sort(rules: list[RuleDef]) -> list[RuleDef]:
    """
    Sort rules in dependency order (DAG) so that a rule runs after its dependents.
    """
    rule_map = {r.id: r for r in rules}
    visited: set[str] = set()
    sorted_rules: list[RuleDef] = []

    def _visit(rule_id: str) -> None:
        if rule_id in visited:
            return
        visited.add(rule_id)
        rule = rule_map.get(rule_id)
        if rule:
            for dep_id in rule.depends_on:
                _visit(dep_id)
            sorted_rules.append(rule)

    for rule in rules:
        _visit(rule.id)

    return sorted_rules


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_rules(
    analysis: SupplyChainAnalysis,
    jurisdiction: str | None = None,
    rules_config_path: str | None = None,
) -> RuleResult:
    """
    Execute all applicable rules against the validated analysis object.

    Args:
        analysis: A fully validated ``SupplyChainAnalysis`` instance.
        jurisdiction: Optional ISO country / region code to scope rules.
        rules_config_path: Path to YAML rules config. Defaults to env var.

    Returns:
        ``RuleResult`` with audit trail, violations, warnings, and mutated analysis.
    """
    # Snapshot before
    snapshot_before = analysis.model_dump()

    # Load rules
    rules = load_rules_config(rules_config_path)

    # Compute confidence tier
    confidence = analysis.ai_analysis.confidence_score
    tier, tier_reason = _compute_tier(confidence)
    analysis.system_status.pipeline_step = f"TIER_{tier}"

    result = RuleResult(
        analysis=analysis,
        tier=tier,
        tier_reason=tier_reason,
        snapshot_before=snapshot_before,
    )

    # Handle BLOCK tier immediately
    if tier == "BLOCK":
        for a in analysis.actions:
            a.status = "BLOCKED_LOW_CONFIDENCE"
            result.blocked_actions.append(a.action_id)
        msg = f"Confidence {confidence:.3f} below 0.50 — all actions blocked."
        result.violations.append(msg)
        result.applied_rules.append(f"TIER={tier}: {tier_reason}")
        result.snapshot_after = analysis.model_dump()
        return result

    # Handle SUGGEST tier — block high-risk actions
    if tier == "SUGGEST":
        for a in analysis.actions:
            if a.payload.get("priority") == "Critical":
                a.status = "BLOCKED_LOW_CONFIDENCE"
                result.blocked_actions.append(a.action_id)
        result.warnings.append(f"SUGGEST tier: Critical actions blocked pending human review.")

    # Handle ESCALATE tier — block all actions
    if tier == "ESCALATE":
        for a in analysis.actions:
            a.status = "BLOCKED_LOW_CONFIDENCE"
            result.blocked_actions.append(a.action_id)
        result.warnings.append(f"ESCALATE tier: All actions blocked. Human review required.")

    # Sort rules in DAG order
    sorted_rules = _topological_sort(rules)

    # Dict representation for field resolution
    analysis_dict = analysis.model_dump()

    # Evaluate each rule
    for rule_def in sorted_rules:
        try:
            evaluate_rule(rule_def, analysis_dict, analysis, result, jurisdiction)
        except Exception as exc:
            warning = (
                f"Rule '{rule_def.id}' raised an error: {exc}"
            )
            result.warnings.append(warning)
            logger.exception(warning)

    # Snapshot after
    result.snapshot_after = analysis.model_dump()

    logger.info(
        "Rules engine complete. Rules fired: %d | Violations: %d | Warnings: %d | Tier: %s",
        len(result.applied_rules),
        len(result.violations),
        len(result.warnings),
        result.tier,
    )

    return result


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------

evaluate_business_rules = run_rules