# Actionable Build Brief
## Phase 1 Office Ticket Automation Prototype

Prepared: June 25, 2026

## 1) Objective
Build and launch a small, office-only prototype in 4 to 6 weeks that:

1. Accepts ticket image uploads
2. Extracts fields with OCR
3. Routes low-confidence/exception items to human review
4. Writes validated records to SharePoint/Excel workflow
5. Generates invoice PDFs from approved records
6. Exports daily CSV files to an on-prem server folder (optional but planned)

## 2) Recommended Architecture (Pilot)
Primary choice: Microsoft-centric serverless pipeline for speed and low implementation risk in this environment.

### Why this option first
- Existing SharePoint usage reduces change management
- Direct fit with Microsoft 365 identity/permissions
- Fastest path to pilot with fewer custom services
- Easier to evolve into deeper custom architecture later

### High-level flow
1. Office uploads ticket image(s) to SharePoint intake library
2. Trigger launches OCR processing workflow
3. OCR extracts structured fields + confidence scores
4. Validation and dedup checks run
5. High-confidence records auto-write to master list/table
6. Low-confidence and exception records route to review queue
7. Reviewer corrects/approves records
8. Invoice PDF is generated from approved records
9. Daily export job writes CSV to on-prem folder (if enabled)

## 3) Canonical Data Model (Phase 1)
Required fields:
- ticket_id (text, unique)
- ticket_date
- truck_or_plate
- material_type
- gross_weight
- tare_weight
- net_weight
- source_site
- destination_site
- vendor_or_driver_name (if present)
- ocr_confidence_score
- review_status (auto_approved, manual_review, approved, rejected)
- invoice_number
- invoice_status (not_generated, generated, exported)
- source_image_path
- created_at
- updated_at

Implementation notes:
- Keep identifiers as text to preserve leading zeros
- Enforce uniqueness on ticket_id + date (or hash key fallback)
- Keep an audit trail for corrected fields and reviewer identity

## 4) 4-6 Week Delivery Plan

### Week 1 - Environment and Foundations
- Confirm target SharePoint site, library, and list/table schema
- Create app registration and minimum required M365 permissions
- Define field mapping from ticket image to canonical data model
- Establish sample ticket set (good quality + bad quality examples)
- Finalize invoice template requirements

Exit criteria:
- SharePoint structure approved
- Security/permissions approved by IT
- Field mapping signed off

### Week 2 - OCR Pipeline and Validation Core
- Implement upload trigger and OCR processing
- Store raw OCR output and normalized fields
- Add confidence thresholds and routing logic
- Implement dedup check strategy (ticket keys/hash)

Exit criteria:
- OCR and normalization running end-to-end
- Confidence-based routing active
- Duplicate detection operational

### Week 3 - Human Review Queue and Spreadsheet Sync
- Build office review interface/queue workflow
- Enable correction + approve/reject actions
- Write approved records to SharePoint master list and Excel table format
- Add error handling and retry behavior for write failures

Exit criteria:
- Review queue functional
- Approved data consistently lands in SharePoint/Excel
- Failures are logged and retryable

### Week 4 - Invoicing and On-Prem Export
- Implement invoice PDF generation from approved records
- Add invoice numbering and status tracking
- Implement scheduled CSV export to on-prem folder (or mock if IT dependency blocks)
- Validate month-end style batch process

Exit criteria:
- Invoice generation live
- Export path proven (or blocked item documented with workaround)

### Week 5 - Hardening and UAT
- Load/performance checks on realistic weekly volume
- Improve handling for edge cases (blurry scans, missing fields)
- User acceptance testing with office staff
- Update SOP and quick reference guide

Exit criteria:
- UAT sign-off
- Pilot metrics measurable

### Week 6 (if needed) - Buffer and Production Readiness
- Fix defects from UAT
- Security review wrap-up
- Go-live checklist and handoff

Exit criteria:
- Pilot ready for controlled production use

## 5) MVP Backlog

### Must-have (Phase 1)
1. SharePoint intake upload workflow
2. OCR extraction and normalization
3. Confidence threshold routing
4. Duplicate detection
5. Human review queue with approve/reject
6. SharePoint/Excel write-back of approved records
7. Invoice PDF generation and numbering
8. Daily CSV export to on-prem folder (or documented temporary manual equivalent)
9. Audit log for corrections and status changes
10. Operational dashboard: counts by status and processing errors

### Should-have (if time allows)
1. Batch reprocess for failed OCR items
2. Configurable confidence threshold by ticket type
3. Exception reason categorization
4. Basic reconciliation report (tickets processed vs invoiced)

### Phase 2 (defer)
1. Driver-side portal/app
2. Dispatch or fleet workflows
3. Real-time ERP/accounting direct API sync
4. Multi-template invoicing by customer contract rules
5. Advanced analytics and forecasting

## 6) Acceptance Criteria for Pilot Success
1. Administrative time reduction >= 60% versus current manual entry
2. Final invoice data accuracy = 100% after review/approval
3. Export reliability >= 99% scheduled runs without manual intervention
4. OCR auto-approval rate reaches agreed target after tuning (example: >= 70%)
5. All exceptions remain traceable with clear owner/status

## 7) Key Risks and Mitigations

### Risk: OCR quality variability
Mitigation:
- Use confidence threshold routing
- Keep human review mandatory for low-confidence records
- Maintain model tuning set from real ticket samples

### Risk: SharePoint/Excel concurrency and lock/throttle behavior
Mitigation:
- Queue writes and use retry with backoff
- Prefer append/update patterns that reduce collisions
- Add idempotency key per ticket

### Risk: On-prem export dependency on IT/network setup
Mitigation:
- Plan early IT validation for gateway/service account/folder permissions
- Provide temporary manual export fallback for pilot continuity

### Risk: Scope creep into full TMS features
Mitigation:
- Enforce office-only scope and change-control gate

## 8) External Vendor Benchmark Plan (TruckIT-first)
Use TruckIT demo outputs as process input to this prototype, not as immediate replacement decision.

Capture from demo:
1. Office intake fields and validation rules
2. Exception handling patterns
3. Approval and audit workflows
4. Invoice grouping and numbering logic
5. Integration constraints (API/webhooks/rate limits)

## 9) Decisions Needed This Week
1. Confirm SharePoint site/library and ownership
2. Confirm invoice template format and required fields
3. Confirm on-prem export target path and IT owner
4. Confirm success metrics and pilot volume target
5. Confirm who signs off on UAT

## 10) Deliverables at Pilot Completion
1. Working office-side prototype in production-like environment
2. SharePoint/Excel integrated data flow
3. Invoice PDF generation pipeline
4. On-prem export workflow (live or approved fallback)
5. SOP + runbook + support checklist
6. Go/no-go recommendation for Phase 2
