"""
Tests for the Supply Chain Compliance Pipeline using the Mock AI Agent.

Runs all three scenarios through validation and business rules, printing
detailed results for manual verification.
"""

from src.agent_mock import MockAiAgent
from src.models import parse_agent_output
from src.rules import run_rules


def test_layer_behaviors():
    print("=== STARTING MOCK AI AGENT PIPELINE RUN ===\n")
    
    scenarios = ["TARIFF_SPIKE_CRITICAL", "LOW_CONFIDENCE_MALFORMED", "INVALID_JSON_RETRY"]
    
    for scenario in scenarios:
        print(f"--- Testing Scenario: {scenario} ---")
        
        # 1. Fetch data from our Mock API instead of your partner's real agent
        raw_agent_string = MockAiAgent.get_mock_response(scenario)
        
        # 2. Fire up the Validation Engine (models.py)
        parsed_result = parse_agent_output(raw_agent_string)
        
        if isinstance(parsed_result, str):
            print(f"❌ Validation Engine Successfully Caught an Error Profile!")
            print(f"   Error response: {parsed_result[:200]}...\n")
            continue
            
        print("✅ Validation Engine Passed: Structural Schema Matches Perfectly.")
        
        # 3. Fire up the Business Rules Engine (rules.py)
        rule_result = run_rules(parsed_result)
        print(f"   Applied Audit Rules List: {rule_result.applied_rules}")
        print(f"   Actions Blocked by Safety Guardrails: {[a for a in rule_result.analysis.actions if a.status != 'PENDING']}")
        
        # Confirm Rule 1 Mutated Priority to Critical
        for action in rule_result.analysis.actions:
            print(f"   [*] Evaluated Action '{action.action_id}' targeting '{action.target_system}':")
            print(f"       Status Set to -> {action.status}")
            print(f"       Priority Set to -> {action.payload.get('priority', 'Default')}")
            if "escalation_reason" in action.payload:
                print(f"       Escalation Reason -> {action.payload['escalation_reason']}")
        print("\n")


if __name__ == "__main__":
    test_layer_behaviors()