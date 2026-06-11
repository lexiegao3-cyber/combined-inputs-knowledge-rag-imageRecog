# U.S. Country of Origin Marking and Documentation Policy

## Sources
- 19 CFR Part 134, Country of Origin Marking: https://www.ecfr.gov/current/title-19/chapter-I/part-134
- 19 U.S.C. 1304, Marking of imported articles and containers: https://uscode.house.gov/view.xhtml?req=granuleid:USC-prelim-title19-section1304

## Regulatory Summary
Imported foreign-origin articles generally must be marked with the English name of the country of origin unless an exception applies. Country of origin is generally the country of manufacture, production, or growth. Work performed in another country changes origin only if it creates a substantial transformation.

Under 19 CFR Part 134, noncompliant marking can lead to CBP withholding delivery, redelivery demands after release, marking correction requirements, or additional duty exposure.

## Retrieval Keywords
country of origin, COO, certificate of origin, origin declaration, origin unknown, origin mismatch, made in, substantial transformation, marking, China origin, Vietnam origin, Mexico origin, supplier declaration, customs hold, CBP marking.

## Risk Triggers
- Missing country of origin certificate or declaration.
- Invoice, packing list, purchase order, or label shows conflicting origin.
- Supplier cannot confirm origin.
- Goods are China-linked but documents claim another country without transformation evidence.
- Customs broker requests origin support or says shipment may be held.

## Suggested RAG Output
- Create `compliance_items.type = "COUNTRY_OF_ORIGIN"`.
- Use `status = "MISSING"` when certificate or declaration is absent.
- Use `severity = "HIGH"` if clearance depends on the missing origin document.
- Create a `DELAY` risk if customs hold or release delay is mentioned.
- Create a Slack action for logistics.
- Create a JIRA action to request origin documentation from supplier or customs broker.
