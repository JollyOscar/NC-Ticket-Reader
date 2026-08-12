# Ongoing Cost Breakdown (Phase 1 Pilot)

## Pricing Basis

These figures use public vendor pricing published in USD unless noted otherwise.
Final CAD spend will vary with exchange rate and taxes.

## Phase 1 Usage Assumptions

- Office-only workflow (no driver app)
- About 1,000 ticket images per month to start
- OCR reads primarily from uploaded photos/scans
- Ticket images and invoice PDFs retained in cloud storage
- Spreadsheet master lives in SharePoint/Excel Online
- On-prem server receives optional CSV exports when needed

## Itemized Monthly Costs

| Tool | Plan / Unit Price | Pilot Estimate | Notes |
| --- | --- | --- | --- |
| Cloudflare Pages | Free, $0/month | $0 | Frontend hosting should remain free. |
| Cloudflare Workers/Functions | Usage-based, paid tier as needed | $0-$5 | Depends on API call volume and execution usage. |
| Google Vision OCR | First 1,000 images/month free, then $1.50 per 1,000 images | $0-$3 | Main variable cost is OCR volume. |
| Cloudflare R2 storage | $0.015 per GB-month, first 10 GB-month free | $0-$2 | Usually low unless archive size grows quickly. |
| Spreadsheet platform | Existing Microsoft 365 (SharePoint/Excel) or Google account | $0 incremental | Usually already part of existing business tooling. |
| On-prem sync (optional) | Scheduled export job to server share | Usually $0-$5 cloud-side | Cloud cost is low; effort is mostly implementation/network setup. |

## Practical Monthly Total

A realistic early-production cost is usually around **$5-$20 USD/month** for this Phase 1 pilot.

If Nova requires secure connectivity controls between cloud services and the on-prem environment (VPN, gateway, firewall policy work), that is typically a one-time implementation effort rather than a major monthly platform cost.

## Example Scenarios

### Low Usage
- Workers/Functions: $0
- OCR: $0
- R2: $0-$1
- Hosting: $0
- Estimated total: about $0-$2 USD/month

### Typical Pilot
- Workers/Functions: $2-$5
- OCR: $0-$1.50
- R2: $0-$2
- Hosting: $0
- Estimated total: about $5-$9 USD/month

### Growth Scenario
- Workers/Functions: $5+
- OCR: $1.50-$6
- R2: $1-$3
- Hosting: $0
- Estimated total: about $10-$20+ USD/month

## Commercial Platform Check (TruckIT / Treads)

If Nova chooses a full platform instead of custom build, monthly cost structure is typically different:

- Per-user seat pricing
- Implementation/onboarding fees
- Possible contract minimums
- Optional add-on costs for integrations and payments

For accurate buy-vs-build comparison, request:

- Full annual cost at current user count
- One-time implementation fees
- Contract length and cancellation terms
- Any per-ticket transaction costs

## Important Notes

- OCR usage is still the primary variable for a custom pilot.
- Storage remains low-cost for ticket/invoice archiving at this scale.
- SharePoint integration should fit existing Microsoft licensing in most cases.
- On-prem requirements usually affect setup effort and timeline more than recurring cloud spend.
- A custom Phase 1 keeps monthly costs low while proving business value before larger rollout decisions.
