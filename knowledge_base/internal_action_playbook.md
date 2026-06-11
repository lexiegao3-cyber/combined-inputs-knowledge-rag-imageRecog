# U.S. Supply Chain Compliance Action Playbook

## Purpose
This playbook maps U.S. import compliance risks to operational actions that the RAG agent may recommend. It should help the model choose valid `actions` for the `SupplyChainAnalysis` schema.

## Approved Target Systems
- JIRA
- SLACK
- EMAIL
- SAP

## Tariff and Classification Actions
If tariff exposure is greater than 100000 USD:
- Create a JIRA compliance review ticket.
- Set priority to High or Critical.
- Notify finance by EMAIL.
- Include HTS code, product description, country of origin, estimated exposure, and broker notes in the action payload.

If HTS code is missing or disputed:
- Create a JIRA action for classification review.
- Ask customs broker or trade compliance owner for ruling support or classification basis.

## Country of Origin Actions
If COO certificate or origin declaration is missing:
- Send a SLACK alert to logistics.
- Create a JIRA task to request COO documentation from supplier.
- If shipment is at port or under CBP review, create a SAP action to flag shipment for compliance hold.

## Chemical Import Actions
If chemical import documentation is incomplete:
- Create a JIRA task requesting SDS, CAS number, product composition, and TSCA certification.
- Use EMAIL to notify compliance owner if restricted chemicals are mentioned.
- Do not recommend release until EPA/TSCA status is confirmed.

## Forced Labor Actions
If shipment mentions Xinjiang, XUAR, cotton, polysilicon, solar, tomatoes, apparel, or entities with forced labor risk:
- Create a JIRA supply chain due diligence task.
- Request supplier traceability documents.
- Notify legal/compliance by EMAIL.
- Do not mark automated action as completed without human review.

## Delay Actions
If customs hold, document mismatch, or deadline within 72 hours is mentioned:
- Send immediate SLACK alert to logistics.
- Create JIRA document correction task.
- Estimate financial exposure from demurrage, detention, storage, expedited freight, or production disruption when available.
