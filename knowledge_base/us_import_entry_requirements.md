# U.S. Import Entry Documentation Requirements

## Sources
- 19 CFR Part 141, Entry of Merchandise: https://www.ecfr.gov/current/title-19/chapter-I/part-141
- 19 CFR Part 142, Entry Process: https://www.ecfr.gov/current/title-19/chapter-I/part-142
- CBP Automated Commercial Environment (ACE): https://www.cbp.gov/trade/automated

## Regulatory Summary
U.S. imports require entry or entry summary documentation sufficient for CBP to release merchandise, assess duties, collect statistics, and determine whether legal and regulatory requirements are met. Core documentation often includes commercial invoice, bill of lading or airway bill, packing list, entry data, HTS classification, value, country of origin, importer information, and any partner government agency data.

## Retrieval Keywords
entry, entry summary, ACE, commercial invoice, bill of lading, airway bill, packing list, importer of record, IOR, HTS, declared value, manifest, release, entry documentation, missing invoice, pro forma invoice, customs broker.

## Risk Triggers
- Missing commercial invoice, bill of lading, airway bill, or packing list.
- HTS code, declared value, quantity, or country of origin is missing or inconsistent.
- Broker asks for corrected invoice or entry data.
- Entry cannot be filed or release cannot be obtained.
- Document mentions CBP review, pending ACE filing, or partner government agency hold.

## Suggested RAG Output
- Create `compliance_items.type = "IMPORT_DOCUMENTATION"`.
- Use `regulatory_body = "US_CBP"`.
- Create a `DELAY` risk when missing documentation may delay release.
- Create a JIRA action for broker/document correction.
- Create a Slack alert if delivery deadline is within 72 hours.
