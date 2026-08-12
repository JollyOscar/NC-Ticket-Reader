# V1 Implementation Checklist
## Office Ticket OCR App (Build Order)

Prepared: 2026-06-25

## Product Goal
A small office-only app where staff:
1. Sign in with Microsoft account
2. Upload ticket image
3. Review OCR output against a digital ticket view
4. Confirm/correct fields
5. Save approved record to SharePoint data target
6. Generate invoice-ready status
7. Export CSV for downstream processes

## Recommended V1 Workflow
1. User uploads ticket image
2. OCR extracts fields and confidence
3. App renders digital ticket form (same field layout as paper ticket)
4. User confirms or edits
5. App validates required and numeric fields
6. App writes approved row to SharePoint target
7. App creates invoice status and audit log
8. App includes row in scheduled CSV export batch

## Build Order

### Phase A - Identity and Access
- Add Microsoft Entra ID login
- Restrict allowed users to office group (2-5 users)
- Save user identity for audit trail fields: created_by, reviewed_by

Done when:
- Unauthorized users cannot enter app
- Authorized users sign in with existing Microsoft credentials

### Phase B - Data Model and Storage
Create these entities:

1. ticket_uploads
- upload_id
- original_file_name
- blob_path_or_file_ref
- uploaded_by
- uploaded_at

2. ticket_extractions
- extraction_id
- upload_id
- ocr_provider
- confidence_score
- extracted_json
- parse_status
- created_at

3. ticket_records (canonical approved/editable record)
- ticket_id
- ticket_date
- job_no
- quarry_name
- license_plate
- trucker
- sold_to
- deliver_to
- material_type
- gross_weight
- tare_weight
- net_weight
- received_by
- review_status (needs_review, approved, rejected)
- invoice_status (not_generated, generated, exported)
- reviewed_by
- reviewed_at
- dedup_key

4. audit_log
- event_id
- ticket_record_id
- action
- old_value_json
- new_value_json
- actor
- timestamp

Done when:
- Every update is traceable
- Dedup key is enforced

### Phase C - OCR Integration
- Keep provider abstraction: mock or google_vision
- Parse OCR text into canonical ticket fields
- Save raw OCR result + normalized result

Done when:
- Ticket image returns parsed fields and confidence
- Provider used is visible in UI and logs

### Phase D - Review UI (Core Screen)
Create one review screen with three panes:
1. Left: uploaded ticket image
2. Center: digital ticket form (field-for-field layout)
3. Right: confidence and validation warnings

Actions:
- Approve
- Reject
- Save draft

Validation:
- Required fields not empty
- Numeric fields valid
- net = gross - tare check
- Duplicate detection warning

Done when:
- Reviewer can correct and approve in under 30 seconds for normal tickets

### Phase E - SharePoint Writeback
- Use Microsoft Graph to write approved rows to SharePoint list or Excel table
- Handle write retries with backoff
- Add idempotency key to avoid duplicate writes

Done when:
- Approved ticket appears in SharePoint target exactly once

### Phase F - CSV Export
- Nightly or on-demand export of approved/generated rows not yet exported
- Include exported_at marker on success

Done when:
- CSV is generated and rows are marked exported

## API/Service Boundaries (Minimal)
1. POST /upload
- Accept image
- Store file
- Trigger OCR

2. POST /ocr/process/{upload_id}
- Run OCR
- Save extraction + confidence

3. GET /tickets/{id}
- Return digital ticket payload + confidence + image ref

4. POST /tickets/{id}/approve
- Validate fields
- Save approved record
- Queue SharePoint write

5. POST /tickets/{id}/reject
- Save rejected status + reason

6. POST /exports/csv
- Export unexported approved rows

## Confidence and Confirmation Policy
For V1:
- Show the confirmation/edit screen for 100 percent of tickets.
- Even high-confidence tickets should require one-click human confirm initially.

Why:
- Builds trust with office staff early
- Catches parser-format mistakes confidence alone misses
- Produces correction data to tune OCR logic

After 2-4 weeks of data:
- Allow optional auto-approve only for tickets passing strict rules
- Keep spot-check sampling and manual override

## Bulk Processing (End-of-Day Batches)
They do not need to accept one-by-one OCR speed as a hard limit.
Design the workflow as asynchronous batch processing.

### Throughput Improvements
1. Batch upload mode
- Allow multi-file drag/drop and folder upload
- Show queued count immediately

2. Background OCR workers
- Process tickets in parallel worker jobs instead of serial UI blocking
- Keep UI responsive while OCR runs

3. Queue + status tracking
- States: queued, processing, needs_review, auto_ready, approved, failed
- Show live counters and estimated completion

4. Confidence triage
- Auto-route high-confidence records to an auto-ready bucket
- Route lower-confidence records to manual queue
- Reviewers work only exceptions first

5. Fast review tools
- Keyboard shortcuts (approve, reject, next)
- Side-by-side image + digital ticket
- Highlight only low-confidence fields for quick correction

6. Bulk actions with safeguards
- Bulk approve all auto-ready records after quick spot-check
- Keep duplicate and net-weight validation hard blocks

7. Export batching
- Export only approved and unexported records in one job
- Mark exported_at to avoid duplicate exports

8. Retry and failure handling
- Auto-retry transient OCR/API failures
- Send hard failures to a small reprocess queue

### Practical Performance Targets
- 100-ticket batch should upload in minutes and process in background
- Review time should be dominated by exceptions, not every record
- Office staff should only touch records that fail confidence/rule checks

### Suggested Rollout
Phase 1:
- Human confirm for all records while building trust

Phase 2:
- Auto-approve strict-pass records + manual review for exceptions

Phase 3:
- Add SLA monitoring (batch completion time, failure rate, review backlog)

## Digital Ticket UI Recommendation
Yes: present a digital one-for-one field copy of the ticket details for cross-reference.

Implementation guidance:
- Match paper ticket field order and labels
- Keep fields as editable text boxes
- Highlight low-confidence fields in yellow/red
- Show original OCR text snippet on hover for each field
- Include quick action buttons: "Approve", "Reject", "Save and Next"

Do not attempt pixel-perfect design copy in V1.
Prioritize field parity and speed of review.

## Definition of Done for V1
1. Office user logs in using Microsoft account
2. Uploads ticket image
3. Sees digital ticket review form with OCR output
4. Edits and approves
5. Approved row writes to SharePoint target
6. Row can be exported in CSV batch
7. Audit trail exists for all edits and approvals

## First Week Task Breakdown
Day 1
- Entra login + user allowlist
- Data model finalization

Day 2
- OCR integration and normalized parser
- Save extraction results

Day 3
- Review screen (image + digital form + validation)
- Approve/reject actions

Day 4
- SharePoint writeback integration
- Dedup and retry handling

Day 5
- CSV export + audit log checks
- Demo run with real ticket samples
