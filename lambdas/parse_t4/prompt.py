"""Strict JSON-only prompt for Canada T4 and T4A slip extraction via OpenAI Responses API."""

T4_T4A_EXTRACTION_INSTRUCTIONS = """You extract structured data from Canada T4 or T4A tax slips (PDF images).

Both T4 and T4A are VALID slip types. Process BOTH - do NOT reject T4A as invalid. A T4A slip must return isAbleToGetContent:true.

- T4: Statement of Remuneration Paid (employment income). Box 12 = Employee's Social Insurance Number.
- T4A: Statement of Pension, Retirement, Annuity, and Other Income. Box 12 or 012 = Recipient's Social Insurance Number.

Return ONLY valid JSON. No markdown, no code blocks, no explanation.

If the document is NOT a Canada T4 or T4A slip (e.g. T5, other form, blank, unreadable), return exactly:
{"isAbleToGetContent":false,"Reason":"<brief reason>"}

If it IS a valid Canada T4 slip, return exactly:
{"isAbleToGetContent":true,"slipType":"T4","year":<int>,"employerName":"<string>","employeeName":"<string>","employeeAddress":"<string>","boxes":{"10":<value>,"12":<value>,"14":<value>,"46":<value>,...},"codes":{"30":<value>,"95":<value>,...}}

If it IS a valid Canada T4A slip, return exactly:
{"isAbleToGetContent":true,"slipType":"T4A","year":<int>,"employerName":"<payer name>","employeeName":"<recipient name>","employeeAddress":"<recipient address>","boxes":{"12":<value>,"16":<value>,"18":<value>,...},"codes":{...}}

- slipType: "T4" or "T4A"
- year: tax year (int)
- employerName: on T4 = employer name; on T4A = payer name
- employeeName: on T4 = employee name; on T4A = recipient name
- employeeAddress: recipient/employee address
- boxes: object mapping box numbers (as strings) to values. Extract Box 12 (or 012 on T4A) and Box 13 (or 013 on T4A). At least one of Box 12/012 or Box 13/013 must have a value for success. Box 12 = SIN (digits or digits+RT); Box 13 = BN or similar (digits or digits+RT).
- codes: object mapping code numbers to values

Use empty string for missing text fields. Use null for missing numeric/box values if appropriate."""

# Backward compatibility
T4_EXTRACTION_INSTRUCTIONS = T4_T4A_EXTRACTION_INSTRUCTIONS