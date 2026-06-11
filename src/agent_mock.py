import datetime

class MockAiAgent:
    """
    Simulates your partner's LangGraph / Bedrock agent layer.
    Returns the exact raw string payloads required to thoroughly stress-test
    your Validation and Rules layers.
    """
    
    @staticmethod
    def get_mock_response(scenario_name: str) -> str:
        timestamp = datetime.datetime.utcnow().isoformat() + "Z"
        
        if scenario_name == "TARIFF_SPIKE_CRITICAL":
            # Triggers: Validation Pass, Rule 1 (Financial Over $100k -> Escalates to Critical)
            return f"""
            {{
              "system_status": {{"status": "SUCCESS", "environment": "local_mvp", "pipeline_step": "AI_COMPLETED", "retry_count": 0}},
              "source_info": {{
                "organization_id": "org_acme_corp",
                "document_id": "doc_bl_9942",
                "source_type": "PDF",
                "filename": "manifest_9942.pdf",
                "ingested_at": "{timestamp}"
              }},
              "ai_analysis": {{
                "confidence_score": 0.95,
                "primary_language": "en",
                "extracted_entities": {{
                  "carrier": "Hamburg Süd",
                  "origin_port": "Port of Ho Chi Minh",
                  "destination_port": "Port of Los Angeles",
                  "sku_affected": "SKU-8842-TEXTILE",
                  "estimated_delivery": "2026-06-25"
                }}
              }},
              "compliance_items": [
                {{"item_id": "c1", "type": "TARIFF_RECLASSIFICATION", "description": "Emergency tariff hike", "status": "FLAGGED", "severity": "HIGH", "regulatory_body": "US CBP"}}
              ],
              "risks": [
                {{"risk_id": "r1", "category": "FINANCIAL_IMPACT", "summary": "Overnight 12% margin compression", "probability": "HIGH", "estimated_cost_usd": 145000.00}}
              ],
              "actions": [
                {{"action_id": "a1", "target_system": "jira", "action_type": "CREATE_TASK", "summary": "Review tariff hit", "payload": {{"project": "OPS"}}, "status": "PENDING"}}
              ]
            }}
            """
            
        elif scenario_name == "LOW_CONFIDENCE_MALFORMED":
            # Triggers: Validation Pass, Rule 2 (Confidence < 0.60 -> Escalates to Human, Blocks Actions)
            return f"""
            {{
              "system_status": {{"status": "SUCCESS", "environment": "local_mvp", "pipeline_step": "AI_COMPLETED", "retry_count": 1}},
              "source_info": {{
                "organization_id": "org_acme_corp",
                "document_id": "doc_smudged_001",
                "source_type": "SCAN",
                "filename": "crumpled_invoice.pdf",
                "ingested_at": "{timestamp}"
              }},
              "ai_analysis": {{
                "confidence_score": 0.42,
                "primary_language": "vi",
                "extracted_entities": {{
                  "carrier": "Unknown",
                  "origin_port": "Port of Hai Phong",
                  "destination_port": null,
                  "sku_affected": "SKU-UNKNOWN",
                  "estimated_delivery": null
                }}
              }},
              "compliance_items": [],
              "risks": [
                {{"risk_id": "r2", "category": "DATA_INTEGRITY", "summary": "Legibility issues on shipping documents", "probability": "HIGH", "estimated_cost_usd": 0.00}}
              ],
              "actions": [
                {{"action_id": "a2", "target_system": "slack", "action_type": "SEND_ALERT", "summary": "Ping manager for manual review", "payload": {{"channel": "#alerts"}}, "status": "PENDING"}}
              ]
            }}
            """

        elif scenario_name == "INVALID_JSON_RETRY":
            # Triggers: Validation Engine Failure (Simulates LLM dropping brackets mid-sentence)
            return """
            {
              "system_status": {"status": "SUCCESS", "pipeline_step": "AI_INCOMPLETE",
              "source_info": {"organization_id": "org_corrupt_data"
            """
            
        else:
            raise ValueError(f"Unknown mock scenario: {scenario_name}")