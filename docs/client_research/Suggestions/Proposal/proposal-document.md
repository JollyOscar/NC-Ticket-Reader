# Project Proposal
## Phase 1: Ticket OCR to Spreadsheet + Invoice Generation

**Prepared for:** Jarrod Thorne, Nova Construction
**Prepared by:** Alex Gamble
**Date:** June 25, 2026

---

## Project Overview

This Phase 1 proposal is a smaller pilot focused only on office-side ticket processing.

The system will let staff upload ticket images, extract key fields using OCR, push records into a spreadsheet (including an existing spreadsheet in SharePoint), and generate invoice PDFs from approved ticket data.

This intentionally excludes driver-facing workflows for now so the owner can review a lower-cost, lower-risk implementation first.

---

## Scope of Work (Phase 1)

Included in this phase:

- Office upload page for ticket images (single and batch upload)
- OCR extraction of ticket fields (date, ticket number, truck/plate, material, gross/tare/net, source site, destination site)
- Review/edit screen for OCR results before final save
- Data output to spreadsheet:
  - CSV export, and/or
  - direct sync into an existing spreadsheet (SharePoint/Excel Online or Google Sheets)
- Optional on-prem handoff:
  - scheduled CSV export to a server folder for existing internal processes
- Invoice PDF generation from approved records
- Invoice numbering format and basic template branding (logo, address, tax fields)
- Deployment and handoff

Out of scope for this phase:

- Driver mobile portal
- Driver-office ticket matching workflow
- Dispatch/fleet optimization features
- Automated payment processing

---

## Development Cost

| | |
| --- | --- |
| Hourly rate | $40 CAD/hour |
| Estimated hours | ~70 hours |
| **Project total** | **$2,800 CAD** |

*Plus applicable taxes. Any approved additions beyond this phase will be quoted separately.*

### Payment Schedule

| Milestone | Due | Amount |
| --- | --- | --- |
| Project kickoff | Upon agreement | $840 CAD (30%) |
| Pilot functional | Upload, OCR, and SharePoint spreadsheet output complete | $1,120 CAD (40%) |
| Final delivery | Invoicing, polish, and deployment complete | $840 CAD (30%) |

---

## Estimated Timeline

Approximately **4 to 6 weeks** from project start to Phase 1 delivery.

---

## Monthly Running Costs (Pilot)

These costs are usage-based and published in USD.

| Service | Purpose | Estimated Monthly Cost |
| --- | --- | --- |
| Cloudflare Pages | Frontend hosting | $0/month (free plan) |
| Cloudflare Workers/Functions | Backend logic and API endpoints | $0-$5 USD/month |
| Cloudflare R2 | Ticket and invoice file storage | $0-$2 USD/month |
| Google Vision (OCR) | Ticket field extraction | First 1,000 images/month free, then ~$1.50 USD per 1,000 images |
| Spreadsheet platform | Existing Microsoft 365 or Google account | Usually $0 incremental |

**Estimated pilot monthly total: approximately $5-$20 USD/month** at expected early usage.

If on-prem server sync requires secure gateway/VPN or custom network hardening, that setup work is implementation-specific and should be scoped separately.

---

## Build vs Buy Checkpoint

You asked for a quick check against **TruckIT** and **Treads**.

### TruckIT

What is clear from public materials:

- Strong bulk-hauling platform positioning
- Includes broader operational modules (dispatch, mobile apps, material management, payments, reporting)
- API/integration-oriented implementation path

Fit for current need:

- Best immediate use is as a benchmark for office-side process design
- For a narrow Phase 1 requirement (OCR to spreadsheet to invoice), may be more platform than needed
- Best next step is a scoped demo focused only on office ticket-to-invoice flow, then mirror the useful patterns in a small custom prototype

### Treads (name to confirm)

The exact product identity should be confirmed before any comparison, because multiple unrelated products include similar naming.

Recommended next step:

- Confirm the exact vendor name and website from your uncle
- Run the same requirements checklist used for TruckIT

### Vendor Demo Checklist (both products)

- Can office staff upload existing paper ticket images in batches?
- Is OCR included natively, and what is the accuracy on real quarry tickets?
- Can records write directly to Nova's existing spreadsheet layout?
- Can records write directly to Excel files stored in SharePoint?
- Can the same data be exported to an on-prem server folder if required?
- Can invoices be generated in Nova's required format?
- Does implementation require drivers to adopt new apps immediately?
- Full pricing: setup cost, per-user fees, per-ticket fees, and contract terms

---

## Proposed Technical Direction for Phase 1 Build

- Lightweight web upload interface for office users
- OCR pipeline for structured field extraction
- Spreadsheet integration layer (CSV export + direct SharePoint spreadsheet sync)
- Optional on-prem export connector (scheduled file drop)
- PDF invoice generation and archive

This keeps the system focused on immediate value while preserving a clean path to add driver workflows later if approved.

---

## Contact

**Alex Gamble**
thealexgamble@gmail.com
1 (902) 956-8112
