# U.S. Tariff and Section 301 Rules

## Sources
- USTR China Section 301 Tariff Actions and Exclusion Process: https://ustr.gov/issue-areas/enforcement/section-301-investigations/tariff-actions
- Harmonized Tariff Schedule of the United States: https://hts.usitc.gov/
- CBP Trade Remedies: https://www.cbp.gov/trade/remedies

## Regulatory Summary
The United States may impose additional duties on certain imported goods under trade remedy programs, including Section 301 actions administered through USTR and enforced at entry by CBP. For goods connected to China, tariff exposure depends on country of origin, HTS classification, product description, entry date, and any valid exclusion.

## Retrieval Keywords
Section 301, USTR, CBP, HTS, HS code, tariff classification, additional duty, trade remedy, China, PRC, Shanghai, Shenzhen, Ningbo, electronics, battery, machinery, semiconductor, industrial component, reclassification, customs broker, duty increase.

## Risk Triggers
- Document mentions China-origin goods and missing, uncertain, or disputed HTS classification.
- Customs broker warns that classification may trigger Section 301 duties.
- Product category includes electronics, batteries, semiconductors, machinery, chemicals, or industrial components.
- Estimated tariff exposure is greater than 100000 USD.
- Invoice, packing list, purchase order, or broker email gives inconsistent product descriptions.

## Suggested RAG Output
- Create `compliance_items.type = "TARIFF_CLASSIFICATION"`.
- Use `regulatory_body = "US_CBP"`.
- Create a `FINANCIAL` risk when additional duty or reclassification exposure is stated or implied.
- Use `probability = "HIGH"` when broker language says likely, pending CBP review, reclassified, or subject to Section 301.
- Create a JIRA action for compliance review.
- Notify finance when estimated exposure exceeds 100000 USD.
