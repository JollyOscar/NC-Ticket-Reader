# Prototype First Steps
## Build-Focused Plan (No Owner Pitch)

Prepared: June 25, 2026

## Goal Right Now
Prove you can build the office-side core workflow quickly:

1. Upload ticket image
2. Extract fields (OCR)
3. Review/edit extracted data
4. Save to spreadsheet workflow (SharePoint/Excel)
5. Generate invoice output record

## What To Demo First (Fastest Credible Version)
Build a thin vertical slice with one ticket type and one invoice template.

Definition of done for first demo:
- One user uploads one ticket image
- System returns extracted fields with confidence values
- User corrects fields in a review screen/form
- Approved result is written to SharePoint list (or Excel table in SharePoint)
- One invoice record is generated from approved row

This is enough to prove feasibility and execution ability.

## Step 1: Lock Input/Output Contract (Day 1)
Do this before writing app logic.

### Input contract (ticket fields)
- ticket_id
- ticket_date
- truck_or_plate
- material_type
- gross_weight
- tare_weight
- net_weight
- source_site
- destination_site

### Output contract (what must exist after approval)
- Approved row in SharePoint/Excel
- invoice_number
- invoice_status
- source_image_reference
- reviewed_by
- reviewed_at

Deliverable:
- Final field mapping table approved by your uncle

## Step 2: Stand Up SharePoint Data Structures (Day 1)
Create two lists or one list plus one intake library.

Minimum structure:
1. Intake document library
- Stores uploaded ticket files

2. Ticket processing list
- Stores extracted fields, confidence, and review status

3. Invoice queue list (or columns in processing list)
- Tracks invoice generation status

Critical columns:
- ticket_id (enforce uniqueness if possible)
- review_status (new, needs_review, approved, rejected)
- confidence_score
- invoice_status (not_generated, generated, exported)

Deliverable:
- SharePoint site path and list schemas finalized

## Step 3: Build OCR + Normalize Function (Day 2)
Implement one processing function/workflow that:
1. Accepts file from intake library
2. Calls OCR service
3. Maps result to canonical fields
4. Computes confidence gate
5. Writes row to processing list

Initial confidence rule:
- confidence >= 0.85 => auto-ready
- confidence < 0.85 => needs_review

Deliverable:
- End-to-end extraction for at least 10 sample tickets

## Step 4: Build Human Review Loop (Day 2-3)
Create a simple review interface (can be SharePoint grid/form first).

Reviewer actions:
- Edit extracted fields
- Mark approved or rejected
- Save reviewer identity and timestamp

Validation checks before approve:
- ticket_id present
- net_weight numeric
- required fields not empty

Deliverable:
- Reviewer can correct and approve low-confidence tickets

## Step 5: Write Approved Data to Spreadsheet Workflow (Day 3)
On approval:
- Write/append to the target SharePoint list or Excel table
- Prevent duplicate rows by ticket_id + date key

Minimum duplicate strategy:
- Create dedup_key = ticket_id + ticket_date
- Reject if key already exists

Deliverable:
- Approved records appear in target spreadsheet destination

## Step 6: Add Invoice Generation Trigger (Day 3-4)
For prototype, invoice generation can be simple:
- Generate invoice_number
- Mark invoice_status generated
- Create a basic invoice row payload for later PDF rendering

If time permits:
- Render basic PDF template

Deliverable:
- Approved ticket gets invoice_number and generated status

## Step 7: Optional On-Prem Export Stub (Day 4)
Do not overbuild this in first demo.

Prototype-ready approach:
- Daily scheduled export builds CSV from approved/generated rows
- Write to designated on-prem folder (or simulate write path if IT access not ready)

Deliverable:
- CSV export job runs and produces expected schema

## What To Show Your Uncle After 3-4 Days
Live demo script:
1. Upload a real ticket scan
2. Show extracted values and confidence
3. Correct one wrong field manually
4. Approve record
5. Show row in SharePoint/Excel target
6. Show invoice number/status generated
7. Show exported CSV row (or staged export output)

This proves you can deliver exactly what he asked for.

## Non-Negotiable Engineering Guardrails
- Keep ticket IDs as text
- Always keep source image reference on each record
- Log every status change with timestamp
- Add idempotency key for safe retries
- Keep scope office-only (no driver features)

## Immediate Task List (Start Today)
1. Confirm final field mapping with uncle (30 mins)
2. Create SharePoint lists/libraries (60 mins)
3. Seed with 20 real sample tickets (30 mins)
4. Implement OCR-to-list pipeline (half day)
5. Implement review/approve flow (half day)
6. Implement approved write + dedup check (half day)
7. Demo and collect feedback

## Success Checkpoint for This Week
You are on track if by end of week you can process a batch of 20 tickets with:
- Accurate final approved output
- No duplicate approved entries
- Clear status for every ticket (new/review/approved/rejected)
- At least one successful invoice generation path
