# U.S. Import Shipping Delay and Customs Release Guidelines

## Sources
- 19 CFR Part 141, Entry of Merchandise: https://www.ecfr.gov/current/title-19/chapter-I/part-141
- 19 CFR Part 142, Entry Process: https://www.ecfr.gov/current/title-19/chapter-I/part-142
- CBP Basic Importing and Exporting: https://www.cbp.gov/trade/basic-import-export
- Federal Maritime Commission: https://www.fmc.gov/

## Regulatory Summary
U.S. import release depends on timely and accurate entry documentation, including commercial invoice data, entry or entry summary information, carrier release information, and any documents required by CBP or partner government agencies. Missing or inconsistent documentation can delay release, cause customs holds, and create storage, demurrage, detention, or expedited freight costs.

## Retrieval Keywords
customs hold, CBP hold, entry summary, ACE, commercial invoice, packing list, bill of lading, airway bill, document mismatch, missing invoice, missing signature, demurrage, detention, port congestion, terminal delay, vessel rollover, container hold, release order, delivery within 72 hours.

## Risk Triggers
- Document says shipment is held, blocked, pending review, or cannot be released.
- Missing invoice, bill of lading, packing list, COO certificate, or agency document.
- Delivery deadline is within 72 hours.
- Port congestion, terminal delay, container availability, demurrage, detention, or storage charges are mentioned.
- Broker asks for corrected documentation.

## Suggested RAG Output
- Create a `DELAY` risk.
- Use `probability = "HIGH"` when shipment is already held or delivery is due within 72 hours.
- Add estimated cost when demurrage, detention, storage, or expedited freight amount is stated.
- Create a Slack logistics alert.
- Create a JIRA action for document correction.
- Use SAP action only when shipment record should be placed on compliance hold.
