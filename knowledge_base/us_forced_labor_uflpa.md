# U.S. Forced Labor and UFLPA Supply Chain Risk

## Sources
- Uyghur Forced Labor Prevention Act, H.R.6256, Congress.gov: https://www.congress.gov/bill/117th-congress/house-bill/6256
- CBP Forced Labor: https://www.cbp.gov/trade/forced-labor
- DHS Forced Labor Enforcement Task Force: https://www.dhs.gov/uflpa

## Regulatory Summary
The United States prohibits imports made wholly or in part with forced labor. The Uyghur Forced Labor Prevention Act creates a heightened risk framework for goods connected to the Xinjiang Uyghur Autonomous Region or listed entities. Importers may need supply chain traceability and due diligence evidence to address detention or exclusion risk.

## Retrieval Keywords
forced labor, UFLPA, Xinjiang, XUAR, Uyghur, Uighur, cotton, apparel, textile, polysilicon, solar panel, tomato, PVC, aluminum, entity list, withhold release order, WRO, supply chain traceability, supplier due diligence.

## Risk Triggers
- Shipment, supplier, manufacturer, or raw material is linked to Xinjiang or XUAR.
- Product category includes cotton, apparel, textiles, solar, polysilicon, tomatoes, PVC, aluminum, or other priority sectors.
- Supplier refuses or cannot provide traceability documentation.
- Document mentions WRO, forced labor, UFLPA review, detention, exclusion, or CBP forced labor inquiry.

## Suggested RAG Output
- Create `compliance_items.type = "FORCED_LABOR_DUE_DILIGENCE"`.
- Use `regulatory_body = "US_CBP"`.
- Create a `COMPLIANCE` risk with `probability = "HIGH"` when Xinjiang, UFLPA, WRO, or supplier traceability failure is mentioned.
- Create a JIRA action requesting supplier traceability and chain-of-custody evidence.
- Create an EMAIL action to notify legal/compliance.
- Do not recommend automated release without human review.
