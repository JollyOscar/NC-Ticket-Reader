# Nova Construction Ticket App

Web application for extracting, reviewing, approving, and exporting quarry ticket data.

## Platform

- Streamlit application deployed on Railway
- Railway Postgres for ticket records and export-batch history
- Railway Bucket for ticket images and CSV exports
- Tesseract OCR by default for low-cost client testing
- Google Vision as an explicit production OCR option

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

## Local development

```bat
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Launch Nova Ticket App.bat
```

The app starts at `http://localhost:8501`.

## Railway deployment

Railway deploys from the `main` branch using the included Dockerfile and `railway.json`.

The production service requires:

- `DATABASE_URL` referencing the Railway Postgres private URL
- `AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET_NAME`, and `AWS_DEFAULT_REGION` from the Railway bucket
- `PORT=8089`, matching the service's Railway domain target port

The live application is available at <https://nc-ticket-reader-production.up.railway.app/>.

## OCR modes

- Default: `pytesseract`, appropriate for public demos and manual review workflows
- Production: `OCR_PROVIDER=google_vision`, requiring a configured Google service account and billing-enabled Vision project

## Verification

```bat
.venv\Scripts\python -m pytest tests -q
```

Generated images, exports, SQLite databases, logs, caches, virtual environments, and credentials are intentionally excluded from source control.
