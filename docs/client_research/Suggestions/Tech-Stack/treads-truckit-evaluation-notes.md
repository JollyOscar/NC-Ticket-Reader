# Treads and TruckIT Evaluation Notes

## Current Context

The requested alternatives from the phone call were:

- TruckIT
- Treads (name likely correct, but exact vendor URL should be confirmed)

Primary intent for TruckIT review:

- Study how they handle office-side ticket intake, validation, spreadsheet flow, and invoice output
- Use those findings to shape a small custom prototype rather than adopting a full platform immediately

## What To Confirm First

Before comparing, verify the exact Treads product identity.
There are multiple unrelated products with similar names.

Minimum confirmation:

- Company name
- Website URL
- Main contact email

## Preliminary View

### TruckIT

Public positioning indicates a broad bulk-hauling operations platform with:

- e-ticketing and workflow digitization
- broader operations modules (dispatch, reporting, payments, integrations)

Implication for Nova:

- Useful as an office-workflow benchmark immediately
- Strong if Nova later wants a full platform rollout
- Potentially larger implementation than needed for this immediate office-only pilot

### Treads

Treat as pending verification until the exact vendor is confirmed.
Apply the same scoring checklist once confirmed.

## Scoring Checklist

Use this exact checklist in demos for both vendors.

1. Can office staff upload historical and new ticket images in bulk?
2. Is OCR included natively, and what is measured accuracy on similar tickets?
3. Can extracted fields be pushed into Nova's existing spreadsheet layout automatically?
4. Can invoice PDFs be generated in Nova's desired format?
5. Can implementation start office-only without requiring driver app adoption?
6. What is total year-1 cost: setup, licenses, support, and integration?
7. What contract terms apply: minimum term, renewal, cancellation?
8. What export options exist if Nova later migrates away?

## Prototype Translation Checklist (after TruckIT demo)

Capture these implementation details from the office-side flow and map them into the custom pilot:

1. Required upload fields and validation rules
2. OCR correction workflow (what fields users edit most)
3. Spreadsheet column layout and naming conventions
4. Invoice structure: grouping, numbering, tax handling, and totals
5. Exception handling: unreadable tickets, duplicate tickets, and missing weights
6. User permissions for office staff and approvers

## Decision Rule

- Recommended now: run TruckIT demo as a process benchmark, then implement a focused custom Phase 1 prototype.
- Revisit platform adoption after the prototype proves volume, accuracy, and user fit.
