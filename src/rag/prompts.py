def build_supply_chain_prompt(raw_text: str, retrieved_context: list[dict]) -> str:
    context_text = "\n\n".join(
        f"Source: {item['source']}\n{item['text']}"
        for item in retrieved_context
    )

    return f"""
You are a supply chain compliance analyst.

Use the raw document and retrieved compliance context to produce a JSON object
that strictly follows the SupplyChainAnalysis schema used by this project.

Do not output markdown.
Do not explain your reasoning.
Only output valid JSON.

Required top-level fields:
- system_status
- source_info
- ai_analysis
- compliance_items
- risks
- actions

Retrieved context:
{context_text}

Raw document:
{raw_text}
"""