"""
Entry point: run the Supply Chain Compliance Pipeline as a module.

Usage:
    python -m src                    # Quick demo with mock data
    python -m src --bus              # Run the ingestion bus (folder connector)
    python -m src --rules-demo       # Show all YAML rules applied
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)

from src.pipeline import run_pipeline, init_db, _MOCK_AGENT_OUTPUT
from src.rules import load_rules_config, run_rules
from src.models import parse_agent_output, SupplyChainAnalysis
from src.ingestion_bus import IngestionBus


def main():
    parser = argparse.ArgumentParser(description="Supply Chain Compliance Platform")
    parser.add_argument("--bus", action="store_true", help="Run the ingestion bus")
    parser.add_argument("--rules-demo", action="store_true", help="Show YAML rules demo")
    parser.add_argument("--health", action="store_true", help="Check connector health")
    args = parser.parse_args()

    if args.health:
        bus = IngestionBus({
            "folder": {"path": "./demo_inputs"},
        })
        print(bus.report())
        return

    if args.bus:
        _run_bus()
        return

    if args.rules_demo:
        _rules_demo()
        return

    _quick_demo()


def _quick_demo():
    """Quick pipeline demo with mock data."""
    print("=" * 70)
    print("  Supply Chain Compliance Pipeline — MVP Demonstration")
    print("=" * 70)
    init_db()
    result = run_pipeline(_MOCK_AGENT_OUTPUT)

    print()
    print(result.summary())

    # Show tier
    print()
    print(f"  ── Confidence Tier: {result.output_data.get('system_status', {}).get('pipeline_step', 'N/A')}")
    if result.output_data:
        rules_count = len(result.output_data.get("risks", []))
        flags_count = len(result.output_data.get("compliance_items", []))
        print(f"  ── Risks: {rules_count} | Compliance Flags: {flags_count}")
    print()


def _rules_demo():
    """Show YAML rules applied against mock data."""
    print("=" * 70)
    print("  YAML-Driven Rules Engine — Demonstration")
    print("=" * 70)
    init_db()

    # Load rules config
    rules = load_rules_config()
    print(f"\n  Loaded {len(rules)} rules from config:")
    for r in rules:
        jurs = ", ".join(r.jurisdictions)
        print(f"    • [{r.id}] {r.name} ({r.severity}) — applies to: {jurs}")

    # Parse mock data
    parsed = parse_agent_output(_MOCK_AGENT_OUTPUT)
    if isinstance(parsed, str):
        print(f"\n  ❌ Validation error: {parsed[:100]}")
        return

    analysis: SupplyChainAnalysis = parsed

    # Run rules
    print(f"\n  Input confidence: {analysis.ai_analysis.confidence_score}")
    result = run_rules(analysis)

    print(f"\n  ── Tier: {result.tier}")
    print(f"     {result.tier_reason}")
    print(f"  ── Rules fired: {len(result.applied_rules)}")
    for rule in result.applied_rules:
        print(f"     ✓ {rule}")
    print(f"  ── Violations: {len(result.violations)}")
    for v in result.violations:
        print(f"     ❌ {v}")
    print(f"  ── Warnings: {len(result.warnings)}")
    for w in result.warnings:
        print(f"     ⚠ {w}")
    print(f"  ── Blocked actions: {len(result.blocked_actions)}")
    for a in result.blocked_actions:
        print(f"     🔒 {a}")
    print(f"  ── New compliance flags added: {len(analysis.compliance_items)}")
    for f in analysis.compliance_items:
        print(f"     🚩 {f.type} ({f.severity}): {f.description[:60]}")
    print()


def _run_bus():
    """Run the ingestion bus with folder connector."""
    print("=" * 70)
    print("  Ingestion Bus — Folder Connector Active")
    print("=" * 70)
    init_db()

    bus = IngestionBus({
        "folder": {"path": "./demo_inputs"},
    })

    results = bus.poll_all()
    print()
    print(bus.report())

    total = sum(len(v) for v in results.values())
    successes = sum(
        1 for res_list in results.values() for r in res_list if r.success
    )
    print(f"  Processed: {total} document(s) | {successes} succeeded")
    print()


if __name__ == "__main__":
    main()