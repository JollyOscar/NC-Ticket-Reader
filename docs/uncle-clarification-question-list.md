# Uncle Clarification Question List
## Office Ticket OCR App (Trimmed Practical Version)

Use this in one call/meeting and capture answers directly under each question.

## Already Assumed (No Need To Ask)
- Current process is manual.
- Tickets are handwritten.
- Review happens on the same screen as the image preview.
- Low-confidence fields should be highlighted.
- Invoice work is in scope immediately.
- You prefer on-prem export in Phase 1 if feasible.

## 1. Current Workflow and Timing
1. Do office staff process tickets as they arrive, at end-of-day, or both?
2. On a typical day, how many tickets are processed?
3. What are the top pain points right now (time, errors, missing tickets, duplicate entry, invoicing delays)?

## 2. Ticket Formats and Variability
1. How many different ticket layouts exist today?
2. Are ticket templates stable, or do quarries/vendors change formats often?
3. Which fields are always present vs sometimes missing?
4. Are there frequent low-quality images (blurry, angled, dark)?
5. Are both front/back of tickets ever needed?
6. Do they need to process multi-page ticket documents?

## 3. Data Capture Rules
1. What exact fields must be captured from every ticket?
2. Should empty fields be allowed for specific columns (for example job number, plate, received by)?
3. What data validation rules should apply (numeric only, date format, allowed material types)?
4. Should net be auto-validated as gross minus tare, and what should happen on mismatch?
5. How should duplicates be defined (ticket id only, ticket id plus date, ticket id plus quarry)?
6. What should happen when a duplicate is detected?

## 4. CSV and Spreadsheet Requirements
1. What columns must be in exported CSV in final production?
2. What column order is required?
3. What date format do they require in CSV?
4. Should numeric values include commas or plain digits?
5. Do they require any legacy column names that cannot change?
6. Where is CSV consumed next (person, system, accounting tool)?
7. Should CSV export be manual, scheduled, or both?
8. If scheduled, what times and timezone?
9. Do they want one CSV per day, per batch, or rolling file append?
10. Do they need separate CSVs per quarry, project, or customer?

## 5. SharePoint and Microsoft 365
1. Where exactly are current spreadsheets stored in SharePoint (site, library, file)?
2. Should app write to SharePoint list, Excel table, or both?
3. Who owns SharePoint permissions and approvals internally?
4. Is Microsoft Entra login required for all users?
5. Do they want only users from a specific group/security role to access app?
6. Are there any restrictions on third-party cloud services (Google Vision, Azure AI, etc.)?

## 6. Users and Permissions
1. How many active users will use this app in first 3 months?
2. How many users upload only vs review/approve?
3. Do they want different permission levels by account?
4. Minimum roles needed: uploader, reviewer, admin?

## 7. Review and Approval UX
1. Should every ticket require human confirmation initially?
2. Which fields are considered critical and must always be reviewed?
3. Should app support optional keyboard shortcuts for faster review later?
4. Should app support bulk approve for high-confidence records later?

## 8. OCR and Accuracy Expectations
1. Are you comfortable with this rollout model:
   - Phase 1: human confirm on every ticket
   - Phase 2: optional auto-approve only for strict pass rules
2. For invoice safety, do you agree we should default low confidence tolerance and route uncertain records to manual review?
4. Do you want raw OCR text kept for troubleshooting, or only final confirmed ticket data?

## 9. Invoicing Requirements
1. Is there existing invoice numbering format to follow?
2. Should invoice output be PDF, spreadsheet output, or integration to accounting system?
3. Should invoices be grouped by customer/date/project?

## 10. On-Prem and Integration Constraints
1. Is on-prem CSV drop required in Phase 1, or acceptable as fallback if IT setup blocks timeline?
2. Exact destination path for on-prem exports (if known now)?
3. Who can connect us with whoever manages that server path and permissions?
4. If export fails, should behavior be: retry plus alert plus manual fallback?
5. How long should exported files be retained?

## 11. Operations, Support, and Audit
1. What audit details are required (who changed what and when)?
2. How long should ticket images and logs be retained?
3. Do they need a simple dashboard (queued, reviewed, approved, exported counts)?

## 12. Nice-to-Have Future Items (Confirm Priority)
1. Auto-approve strict high-confidence tickets.
2. Batch processing dashboard and SLA timers.
3. Search and filter by ticket/customer/date.
4. Reconciliation report (processed vs invoiced vs exported).

## Quick Meeting Script
1. Confirm workflow timing and daily volume.
2. Lock mandatory fields plus CSV schema.
3. Confirm users and permissions.
4. Confirm SharePoint write target.
5. Confirm review policy for phase 1.
6. Confirm OCR provider choice and on-prem export expectation.
