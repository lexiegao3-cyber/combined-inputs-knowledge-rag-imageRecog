# U.S. Hazardous Materials Transportation Rules

## Sources
- PHMSA Hazardous Materials Regulations: https://www.phmsa.dot.gov/standards-rulemaking/hazmat/hazardous-materials-regulations
- 49 CFR Parts 100-185: https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I
- 49 CFR Part 172, Hazardous Materials Table and Hazard Communication: https://www.ecfr.gov/current/title-49/subtitle-B/chapter-I/subchapter-C/part-172

## Regulatory Summary
PHMSA regulates the safe and secure transportation of hazardous materials by air, highway, rail, and vessel. Requirements can include classification, packaging, marking, labeling, placarding, shipping papers, emergency response information, and hazmat employee training.

## Retrieval Keywords
hazmat, hazardous material, dangerous goods, PHMSA, DOT, 49 CFR, UN number, proper shipping name, hazard class, packing group, shipping papers, SDS, lithium battery, corrosive, flammable, oxidizer, toxic, placard, label, limited quantity.

## Risk Triggers
- Product is described as dangerous goods or hazardous material.
- Document includes UN number, hazard class, packing group, or SDS hazard classification.
- Missing shipping papers, proper shipping name, hazard label, placard, or packaging certification.
- Lithium battery shipment lacks battery handling information.
- Chemical shipment lacks SDS or transport classification.

## Suggested RAG Output
- Create `compliance_items.type = "HAZMAT_TRANSPORT"`.
- Use `regulatory_body = "US_DOT_PHMSA"`.
- Create a `COMPLIANCE` or `DELAY` risk if hazmat information is incomplete.
- Create a JIRA action to verify classification, packaging, labeling, and shipping papers.
- Escalate to human review before release or transport if hazard class is unknown.
