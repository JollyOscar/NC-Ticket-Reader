# Nova Construction — Ticket Processing App

An easy-to-use application designed for Nova Construction office staff to digitise, review, and export quarry stone load tickets.

---

## 🚀 How to Start the App (1 Click)

Double-click **`Launch Nova Ticket App.bat`** in this folder.

The app will launch automatically in your web browser at:  
👉 **[http://localhost:8501](http://localhost:8501)**

---

## 📋 What This App Does

1. **Upload Ticket Photos**: Drag & drop batch photos or scans of quarry tickets.
2. **Automated Reading (OCR)**: Google Vision OCR automatically reads key ticket information (Date, Ticket #, Customer, Quarry, Material, Weights, Trucker).
3. **Review & Confirm**: Office staff compare the scanned ticket side-by-side with the digital form, verifying that Gross − Tare = Net.
4. **Approve & Export**: One click exports approved tickets directly into CSV spreadsheets ready for invoicing.

---

## 📁 Repository Guide (Easy Navigation)

```
Nova Construction Ticket App/
├── Launch Nova Ticket App.bat   ← Double-click to run the app!
├── app.py                       ← Main web application interface
├── ocr.py                       ← OCR scanning engine (Google Vision)
├── backend_logging.py           ← Activity and system logger
├── run.bat                      ← App startup script
├── requirements.txt             ← Application dependencies
│
├── data/                        ← Storage for tickets and exports
│   ├── prototype.db             ← Ticket database
│   ├── uploads/                 ← Uploaded ticket images
│   ├── exports/                 ← Downloaded CSV export files
│   └── logs/                    ← System log files
│
├── docs/                        ← Documentation & Client Information
│   ├── v1-implementation-checklist.md
│   ├── uncle-clarification-question-list.md
│   └── client_research/         ← Client background notes and sample ticket images
│
├── scripts/                     ├── Helper scripts
│   ├── run_ticket_demo.py       ← Run an end-to-end automated demo
│   ├── clean_test_data.py       ← Utility to clear test records
│   └── verify_no_hardcoded.py   ← Automated system test
│
└── .venv/                       ← Application environment
```

---

## ⚙️ OCR Settings

- **Google Vision (Recommended)**: High accuracy (~90-95% confidence) with handwriting support.
- **Tesseract (Local Fallback)**: Runs offline if Google Cloud is disconnected.

---

## ❓ Need Help?
Contact Nova Construction IT support or refer to the guides in the `docs/` folder.
