# U.S. Chemical Import Compliance Rules

## Sources
- EPA TSCA Import-Export Requirements: https://www.epa.gov/tsca-import-export-requirements
- EPA Chemicals under TSCA: https://www.epa.gov/chemicals-under-tsca
- 19 CFR Part 12, Special Classes of Merchandise: https://www.ecfr.gov/current/title-19/chapter-I/part-12

## Regulatory Summary
For U.S. imports, chemical substances may be subject to the Toxic Substances Control Act (TSCA), administered by EPA and coordinated with CBP at import. Importers may need to certify that chemical imports comply with TSCA or are not subject to TSCA. Some chemicals have specific restrictions or reporting requirements, including PCBs, asbestos, mercury, and certain high-risk substances.

This file is U.S.-focused. Use separate EU REACH knowledge only for EU-bound shipments.

## Retrieval Keywords
TSCA, EPA, chemical import, import certification, positive certification, negative certification, CAS number, SDS, MSDS, chemical substance, mixture, polymer, PCB, asbestos, mercury, metalworking fluid, hexavalent chromium, new chemical, significant new use, SNUR.

## Risk Triggers
- Chemical product enters the United States and document lacks CAS number, SDS, or TSCA certification.
- Product description includes solvent, resin, pigment, coating, adhesive, additive, polymer, surfactant, or industrial chemical.
- Document mentions PCB, asbestos, mercury, hexavalent chromium, or other specifically restricted chemical.
- Supplier cannot confirm TSCA status.
- Customs broker requests EPA or TSCA documentation.

## Suggested RAG Output
- Create `compliance_items.type = "TSCA_IMPORT_REVIEW"`.
- Use `regulatory_body = "US_EPA"`.
- Create a `COMPLIANCE` risk when TSCA status, CAS number, or SDS is missing.
- Create a JIRA action requesting SDS, CAS number, and TSCA import certification from supplier.
- Escalate to human review before shipment release for restricted or unidentified chemicals.
