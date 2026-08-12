# Recommended Tech Stack (Phase 1)

## Goal

Deliver a small office-side pilot that does only four things well:

- Upload ticket images
- Extract fields with OCR
- Save ticket data to spreadsheet format (including existing SharePoint spreadsheets)
- Generate invoice PDFs

No driver portal in this phase.

## Recommended Stack

| Layer | Recommendation | Why it fits this phase |
| --- | --- | --- |
| Frontend | React + Vite | Simple internal upload/review UI with fast delivery speed. |
| Hosting | Cloudflare Pages | Reliable low-cost hosting. |
| Backend/API | Cloudflare Workers or Pages Functions | Handles OCR calls, parsing, spreadsheet writes, and invoice generation. |
| File Storage | Cloudflare R2 | Cheap storage for uploaded ticket images and generated invoices. |
| OCR | Google Vision Document Text Detection | Strong OCR performance for mixed printed/handwritten ticket data. |
| Spreadsheet Output | Microsoft Graph Excel API (SharePoint/OneDrive) and/or Google Sheets API | Lets Nova keep using its current spreadsheet workflow. |
| On-Prem Integration (Optional) | Scheduled CSV file export to a watched server folder | Supports legacy processes that still run from the on-prem server. |
| Invoice Generation | pdf-lib (or equivalent lightweight PDF library) | Generates branded invoice PDFs programmatically from extracted data. |
| Source Control | GitHub | Standard version control and project history. |

## Minimal Data Model

Even if data is spreadsheet-first, keep a small structured record for each upload:

- ticket_id (text)
- ticket_date
- truck_or_plate
- material_type
- gross_weight
- tare_weight
- net_weight
- source_site
- destination_site
- uploaded_image_path
- invoice_number
- invoice_status

Note: store identifiers like ticket numbers as text so leading zeros are preserved.

## Suggested Project Structure

- Office upload page
- OCR processing endpoint
- Review/edit page for extracted fields
- Spreadsheet export/sync module
- Optional on-prem export module
- Invoice generation module
- File archive for images and invoice PDFs

## Buy vs Build Note: TruckIT and Treads

- TruckIT appears to be a broader heavy-haul operations platform (dispatch, payments, reporting, integrations).
- That can be a strong fit if Nova wants an all-in platform now.
- For this narrow Phase 1 workflow, a custom build can be faster, lower-cost, and easier to control.
- Treads should be treated as a vendor to verify by exact name/URL before scoring, since similar names map to different products.

## Implementation Approach

1. Build office upload and OCR flow first
2. Validate extraction against real Nova tickets
3. Map output to Nova's SharePoint spreadsheet format
4. Add optional on-prem file export for server-side workflows
5. Generate invoice template and run sample month-end test
6. Decide whether to extend custom app or shift to a full commercial suite
