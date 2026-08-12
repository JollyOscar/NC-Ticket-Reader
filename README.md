# Nova Construction Ticket App

Web application for extracting, reviewing, approving, and exporting quarry-ticket data. It is designed for a human-reviewed workflow: OCR proposes values, and a reviewer confirms them before a ticket enters an invoice export.

## Platform

- Streamlit application deployed on Railway
- Railway Postgres for ticket records and export-batch history
- Railway Bucket for ticket images and CSV exports
- Tesseract OCR by default for low-cost client testing
- Google Vision as an explicit production OCR option

## Client workflow

1. Open the live application and select **Upload Tickets**.
2. Upload ticket photos or a PDF. Each PDF page is processed as an individual ticket.
3. Review the OCR result, correct any uncertain values, then approve or reject the ticket.
4. Export approved tickets to CSV for invoicing.
5. Use **Ticket History** to review completed tickets and prior export batches.

OCR is intentionally conservative. A missing or uncertain value should be corrected during review, not inferred from customer-specific rules or previous tickets.

## Repository layout

```text
├── app.py                       # Ticket workflow and storage integration
├── ocr.py                       # OCR extraction and field normalization
├── backend_logging.py           # Application logging
├── Dockerfile                   # Railway container image
├── railway.json                 # Railway runtime configuration
├── requirements.txt             # Python dependencies
├── .env.example                 # Local/deployment environment template
├── Launch Nova Ticket App.bat    # Windows local launcher
├── run.bat                      # Local Streamlit launcher
├── run_google_release.bat       # Local Google Vision launcher
├── data/                        # Ignored local runtime storage
└── tests/                       # Regression tests and ticket fixtures
```

Local runtime data is written under `data/` when cloud services are not configured. In Railway, ticket images and generated CSV files are stored in the configured bucket, while ticket records and export history are stored in Postgres.

## Local development

```bat
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Launch Nova Ticket App.bat
```

The app starts at `http://localhost:8501`.

For local testing with the default, no-billing OCR provider, use `Launch Nova Ticket App.bat` or `run.bat`. To test the Google Vision path locally, configure the service-account credential in `.env` and use `run_google_release.bat`.

## Railway deployment

Railway deploys from the `main` branch using the included Dockerfile and `railway.json`.

The production service requires:

- `DATABASE_URL` referencing the Railway Postgres private URL
- `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET_NAME`, and `AWS_DEFAULT_REGION` from the Railway bucket
- Railway's assigned `PORT`; do not set a fixed `PORT` unless the service's domain target port has been changed to match it

The current Railway domain targets port `8080`; the service must listen on the same port. Railway rebuilds and deploys the service when changes are pushed to `main`.

The live application is available at <https://nc-ticket-reader-production.up.railway.app/>.

## OCR modes

- Default: `pytesseract`, appropriate for public demos and manual review workflows
- Production: `OCR_PROVIDER=google_vision`, requiring a configured Google service account and billing-enabled Vision project

Both modes use the same field parsing and validation path. Google Vision is retained for the paid production release; it is never silently selected for the public demo.

## Verification

```bat
.venv\Scripts\python -m pytest tests -q
```

Before sharing the client link after a deployment, confirm that the Railway deployment is successful and load the home page. A `502` response usually means the application listener and Railway domain target ports differ; check the Railway domain target port and the service `PORT` value first.

Generated images, exports, SQLite databases, logs, caches, virtual environments, and credentials are intentionally excluded from source control. Do not commit `.env` files, Google service-account JSON, Railway credentials, or bucket access keys.
