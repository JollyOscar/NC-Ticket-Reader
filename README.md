# Nova Construction Ticket App

A lightweight web app for reviewing, approving, and exporting quarry ticket data from uploaded ticket images and PDFs.

## Overview

This project is built for office staff to:
- upload ticket images or PDFs,
- run OCR extraction,
- review fields before approval,
- export approved tickets to CSV for downstream invoice workflows.

The public-facing demo mode is intentionally safe and low-cost by default, using local OCR. The Google Vision path remains available as an explicit production option for higher-accuracy processing.

## Repository structure

```text
Nova Construction Ticket App/
├── app.py                       # Streamlit app and ticket workflow
├── backend_logging.py           # Logging utilities
├── ocr.py                       # OCR extraction and normalization logic
├── Dockerfile                   # Railway/container setup
├── railway.json                 # Railway deployment config
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment variable template
├── .gitignore                   # Repo hygiene rules
├── README.md                    # Project overview and instructions
├── Launch Nova Ticket App.bat    # Local Windows shortcut for app startup
├── run.bat                      # Local app launcher
├── run_public_demo.bat          # Demo-safe OCR startup script
├── run_google_release.bat       # Google Vision startup script
├──
├── data/                        # Runtime storage (kept as folders, not committed sample data)
│   ├── uploads/.gitkeep
│   ├── exports/.gitkeep
│   ├── logs/.gitkeep
│   └── .gitkeep
├── docs/                        # Client research, proposal, and implementation notes
│   ├── client_research/
│   ├── google-form-generator.gs
│   ├── google-form-generator-v2.gs
│   ├── google-form-quick-setup.md
│   ├── uncle-clarification-question-list.md
│   └── v1-implementation-checklist.md
├── scripts/                     # Operational/helper scripts
│   ├── clean_test_data.py
│   ├── run_ticket_demo.py
│   └── verify_no_hardcoded.py
├── tests/                       # Regression checks
│   └── test_ocr_default_provider.py
└── .venv/                       # Local virtual environment (not committed)
```

## Local startup

On Windows, run:

```bat
Launch Nova Ticket App.bat
```

or from a terminal:

```bat
python -m streamlit run app.py
```

## Environment notes

Use the .env template to configure deployed or demo settings. The app defaults to a safe local OCR mode unless a paid OCR provider is explicitly enabled.

## Production notes

- Public/demo mode: Tesseract via local OCR
- Production override: `OCR_PROVIDER=google_vision`
- Railway: container deploys from this repo and reads environment variables for cloud services when configured

## Clean repo policy

The project intentionally excludes generated caches, temp debug artifacts, uploaded ticket files, exported CSVs, and secrets from source control. Runtime folders remain in place but are empty unless the app is actively processing data.
