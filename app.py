import csv
import datetime as dt
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
import psycopg2
import streamlit as st
from psycopg2.extras import RealDictCursor
from backend_logging import get_log_path, get_logger, tail_log_lines
from ocr import extract_ticket_data

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "prototype.db"

REQUIRED_FIELDS = [
    "ticket_id",
    "ticket_date",
    "quarry_name",
    "sold_to",
    "net_weight",
]

logger = get_logger("app")


def postgres_enabled() -> bool:
    return bool(os.getenv("DATABASE_URL", "").strip())


def bucket_enabled() -> bool:
    required = [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_S3_BUCKET_NAME",
        "AWS_ENDPOINT_URL",
    ]
    return all(os.getenv(name, "").strip() for name in required)


def _db_param_placeholder_count(count: int) -> str:
    if postgres_enabled():
        return ", ".join("%s" for _ in range(count))
    return ", ".join("?" for _ in range(count))


def duplicates_check_enabled() -> bool:
    return os.getenv("IGNORE_DUPLICATE_CHECK", "").strip().lower() not in {"1", "true", "yes", "on"}


def ensure_paths() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def get_s3_client():
    if not bucket_enabled():
        return None
    addressing_style = os.getenv("AWS_S3_URL_STYLE", "virtual").strip().lower()
    if addressing_style not in {"virtual", "path"}:
        addressing_style = "virtual"
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "auto"),
        config=boto3.session.Config(s3={"addressing_style": addressing_style}),
    )


def upload_to_bucket(local_path: Path, prefix: str) -> Optional[str]:
    if not bucket_enabled():
        return None
    s3 = get_s3_client()
    if s3 is None:
        return None
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    key = f"{prefix.rstrip('/')}/{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}_{local_path.name}"
    try:
        s3.upload_file(str(local_path), bucket_name, key)
        return f"s3://{bucket_name}/{key}"
    except Exception as exc:
        logger.warning("bucket_upload_failed prefix=%s key=%s error=%s", prefix, key, exc)
        return None


def persist_file(local_path: Path, prefix: str) -> str:
    if bucket_enabled():
        bucket_path = upload_to_bucket(local_path, prefix)
        if bucket_path:
            return bucket_path
    return str(local_path)


def load_stored_file(file_reference: str) -> Optional[bytes]:
    if not file_reference.startswith("s3://"):
        local_path = Path(file_reference)
        return local_path.read_bytes() if local_path.exists() else None

    bucket_name, _, key = file_reference.removeprefix("s3://").partition("/")
    s3 = get_s3_client()
    if not s3 or not bucket_name or not key:
        return None
    try:
        return s3.get_object(Bucket=bucket_name, Key=key)["Body"].read()
    except Exception as exc:
        logger.warning("bucket_download_failed reference=%s error=%s", file_reference, exc)
        return None


def _dict_cursor(conn):
    if postgres_enabled():
        return conn.cursor(cursor_factory=RealDictCursor)
    return conn


class PostgresConnection:
    def __init__(self, connection: Any):
        self._connection = connection

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def execute(self, query: str, parameters: Any = None):
        cursor = self._connection.cursor()
        cursor.execute(query.replace("?", "%s"), parameters)
        return cursor


def get_conn() -> Any:
    if postgres_enabled():
        conn = psycopg2.connect(os.getenv("DATABASE_URL"), sslmode="require")
        conn.autocommit = False
        return PostgresConnection(conn)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        if postgres_enabled():
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id SERIAL PRIMARY KEY,
                    ticket_id TEXT,
                    ticket_date TEXT,
                    truck_or_plate TEXT,
                    material_type TEXT,
                    job_no TEXT,
                    quarry_name TEXT,
                    trucker TEXT,
                    sold_to TEXT,
                    deliver_to TEXT,
                    received_by TEXT,
                    gross_weight TEXT,
                    tare_weight TEXT,
                    net_weight TEXT,
                    source_site TEXT,
                    destination_site TEXT,
                    confidence_score DOUBLE PRECISION NOT NULL,
                    ocr_provider TEXT NOT NULL DEFAULT 'mock',
                    review_status TEXT NOT NULL,
                    invoice_number TEXT,
                    invoice_status TEXT NOT NULL DEFAULT 'not_generated',
                    image_path TEXT NOT NULL,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    exported_at TEXT,
                    export_batch_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS export_batches (
                    id SERIAL PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    exported_at TEXT NOT NULL,
                    ticket_count INTEGER NOT NULL
                )
                """
            )
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'tickets'"
            )
            existing = {row[0] for row in cursor.fetchall()}
        else:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id TEXT,
                    ticket_date TEXT,
                    truck_or_plate TEXT,
                    material_type TEXT,
                    job_no TEXT,
                    quarry_name TEXT,
                    trucker TEXT,
                    sold_to TEXT,
                    deliver_to TEXT,
                    received_by TEXT,
                    gross_weight TEXT,
                    tare_weight TEXT,
                    net_weight TEXT,
                    source_site TEXT,
                    destination_site TEXT,
                    confidence_score REAL NOT NULL,
                    ocr_provider TEXT NOT NULL DEFAULT 'mock',
                    review_status TEXT NOT NULL,
                    invoice_number TEXT,
                    invoice_status TEXT NOT NULL DEFAULT 'not_generated',
                    image_path TEXT NOT NULL,
                    reviewed_by TEXT,
                    reviewed_at TEXT,
                    exported_at TEXT,
                    export_batch_id INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS export_batches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT NOT NULL,
                    exported_at TEXT NOT NULL,
                    ticket_count INTEGER NOT NULL
                )
                """
            )
            cursor = conn.execute("PRAGMA table_info(tickets)")
            existing = {row[1] for row in cursor.fetchall()}

        maybe_add = {
            "job_no": "TEXT",
            "quarry_name": "TEXT",
            "trucker": "TEXT",
            "sold_to": "TEXT",
            "deliver_to": "TEXT",
            "received_by": "TEXT",
            "ocr_provider": "TEXT NOT NULL DEFAULT 'mock'",
            "raw_ocr_text": "TEXT",
            "export_batch_id": "INTEGER",
        }
        for col, col_type in maybe_add.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {col} {col_type}")


def fetch_export_batches() -> List[sqlite3.Row]:
    with get_conn() as conn:
        if postgres_enabled():
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM export_batches ORDER BY id DESC")
            return cursor.fetchall()
        return conn.execute("SELECT * FROM export_batches ORDER BY id DESC").fetchall()


def fetch_export_batch_tickets(batch_id: int) -> List[sqlite3.Row]:
    with get_conn() as conn:
        if postgres_enabled():
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM tickets WHERE export_batch_id = %s ORDER BY id ASC",
                (batch_id,),
            )
            return cursor.fetchall()
        return conn.execute(
            "SELECT * FROM tickets WHERE export_batch_id = ? ORDER BY id ASC", (batch_id,)
        ).fetchall()


def reopen_ticket_for_correction(ticket_row_id: int, image_path: Optional[str] = None) -> None:
    now = dt.datetime.utcnow().isoformat()
    with get_conn() as conn:
        if image_path:
            parameters = (image_path, now, ticket_row_id)
            if postgres_enabled():
                conn.execute(
                    """
                    UPDATE tickets
                    SET image_path = %s, review_status = 'needs_review', exported_at = NULL,
                        export_batch_id = NULL, updated_at = %s
                    WHERE id = %s
                    """,
                    parameters,
                )
            else:
                conn.execute(
                    """
                    UPDATE tickets
                    SET image_path = ?, review_status = 'needs_review', exported_at = NULL,
                        export_batch_id = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    parameters,
                )
        else:
            parameters = (now, ticket_row_id)
            if postgres_enabled():
                conn.execute(
                    """
                    UPDATE tickets
                    SET review_status = 'needs_review', exported_at = NULL,
                        export_batch_id = NULL, updated_at = %s
                    WHERE id = %s
                    """,
                    parameters,
                )
            else:
                conn.execute(
                    """
                    UPDATE tickets
                    SET review_status = 'needs_review', exported_at = NULL,
                        export_batch_id = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    parameters,
                )
    logger.info("ticket_reopened_for_correction row_id=%s", ticket_row_id)


def reopen_export_batch(batch_id: int) -> int:
    now = dt.datetime.utcnow().isoformat()
    with get_conn() as conn:
        if postgres_enabled():
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tickets
                SET exported_at = NULL, export_batch_id = NULL, updated_at = %s
                WHERE export_batch_id = %s
                """,
                (now, batch_id),
            )
            rowcount = cursor.rowcount
        else:
            cursor = conn.execute(
                """
                UPDATE tickets
                SET exported_at = NULL, export_batch_id = NULL, updated_at = ?
                WHERE export_batch_id = ?
                """,
                (now, batch_id),
            )
            rowcount = cursor.rowcount
    logger.info("export_batch_reopened batch_id=%s tickets=%s", batch_id, rowcount)
    return rowcount


def insert_ticket(fields: Dict[str, str], confidence_score: float, image_path: str, ocr_provider: str, raw_ocr_text: str = "") -> None:
    status = "auto_ready" if confidence_score >= 0.85 else "needs_review"
    now = dt.datetime.utcnow().isoformat()

    with get_conn() as conn:
        params = (
            fields.get("ticket_id", ""),
            fields.get("ticket_date", ""),
            fields.get("truck_or_plate", ""),
            fields.get("material_type", ""),
            fields.get("job_no", ""),
            fields.get("quarry_name", ""),
            fields.get("trucker", ""),
            fields.get("sold_to", ""),
            fields.get("deliver_to", ""),
            fields.get("received_by", ""),
            fields.get("gross_weight", ""),
            fields.get("tare_weight", ""),
            fields.get("net_weight", ""),
            fields.get("source_site", ""),
            fields.get("destination_site", ""),
            confidence_score,
            ocr_provider,
            status,
            image_path,
            raw_ocr_text,
            now,
            now,
        )
        if postgres_enabled():
            conn.execute(
                """
                INSERT INTO tickets (
                    ticket_id, ticket_date, truck_or_plate, material_type,
                    job_no, quarry_name, trucker, sold_to, deliver_to, received_by,
                    gross_weight, tare_weight, net_weight, source_site,
                    destination_site, confidence_score, ocr_provider, review_status,
                    image_path, raw_ocr_text, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                params,
            )
        else:
            conn.execute(
                """
                INSERT INTO tickets (
                    ticket_id, ticket_date, truck_or_plate, material_type,
                    job_no, quarry_name, trucker, sold_to, deliver_to, received_by,
                    gross_weight, tare_weight, net_weight, source_site,
                    destination_site, confidence_score, ocr_provider, review_status,
                    image_path, raw_ocr_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                params,
            )
    logger.info(
        "ticket_inserted ticket_id=%s provider=%s confidence=%.2f image=%s",
        fields.get("ticket_id", ""),
        ocr_provider,
        confidence_score,
        image_path,
    )


def fetch_tickets(statuses: Optional[List[str]] = None) -> List[sqlite3.Row]:
    with get_conn() as conn:
        if not statuses:
            if postgres_enabled():
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("SELECT * FROM tickets ORDER BY id DESC")
                return cursor.fetchall()
            cursor = conn.execute("SELECT * FROM tickets ORDER BY id DESC")
            return cursor.fetchall()

        placeholders = _db_param_placeholder_count(len(statuses))
        if postgres_enabled():
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                f"SELECT * FROM tickets WHERE review_status IN ({placeholders}) ORDER BY id DESC",
                statuses,
            )
            return cursor.fetchall()

        cursor = conn.execute(
            f"SELECT * FROM tickets WHERE review_status IN ({placeholders}) ORDER BY id DESC",
            statuses,
        )
        return cursor.fetchall()


def fetch_ticket(ticket_row_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        l = (ticket_row_id,)
        if postgres_enabled():
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM tickets WHERE id = %s", l)
            row = cursor.fetchone()
        else:
            cursor = conn.execute("SELECT * FROM tickets WHERE id = ?", l)
            row = cursor.fetchone()
    return row


def ticket_exists(ticket_id: str, ticket_date: str, exclude_id: int) -> bool:
    if not duplicates_check_enabled():
        return False

    with get_conn() as conn:
        if postgres_enabled():
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM tickets
                WHERE ticket_id = %s
                  AND ticket_date = %s
                  AND review_status = 'approved'
                  AND id != %s
                """,
                (ticket_id, ticket_date, exclude_id),
            )
        else:
            cursor = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM tickets
                WHERE ticket_id = ?
                  AND ticket_date = ?
                  AND review_status = 'approved'
                  AND id != ?
                """,
                (ticket_id, ticket_date, exclude_id),
            )
        result = cursor.fetchone()
    return bool(result["cnt"] if isinstance(result, dict) else result[0])


def approve_ticket(ticket_row_id: int, edited: Dict[str, str]) -> Optional[str]:
    if ticket_exists(edited["ticket_id"], edited["ticket_date"], ticket_row_id):
        logger.warning(
            "ticket_approve_blocked_duplicate row_id=%s ticket_id=%s date=%s",
            ticket_row_id,
            edited.get("ticket_id", ""),
            edited.get("ticket_date", ""),
        )
        return "Duplicate: an approved ticket with this number and date already exists."

    now = dt.datetime.utcnow().isoformat()

    with get_conn() as conn:
        params = (
            edited["ticket_id"],
            edited["ticket_date"],
            edited.get("truck_or_plate", ""),
            edited["material_type"],
            edited.get("job_no", ""),
            edited.get("quarry_name", ""),
            edited.get("trucker", ""),
            edited["sold_to"],
            edited.get("deliver_to", ""),
            edited.get("received_by", ""),
            edited["gross_weight"],
            edited["tare_weight"],
            edited["net_weight"],
            edited.get("quarry_name", ""),
            edited.get("deliver_to", ""),
            now,
            now,
            ticket_row_id,
        )
        if postgres_enabled():
            conn.execute(
                """
                UPDATE tickets
                SET ticket_id = %s,
                    ticket_date = %s,
                    truck_or_plate = %s,
                    material_type = %s,
                    job_no = %s,
                    quarry_name = %s,
                    trucker = %s,
                    sold_to = %s,
                    deliver_to = %s,
                    received_by = %s,
                    gross_weight = %s,
                    tare_weight = %s,
                    net_weight = %s,
                    source_site = %s,
                    destination_site = %s,
                    review_status = 'approved',
                    reviewed_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                params,
            )
        else:
            conn.execute(
                """
                UPDATE tickets
                SET ticket_id = ?,
                    ticket_date = ?,
                    truck_or_plate = ?,
                    material_type = ?,
                    job_no = ?,
                    quarry_name = ?,
                    trucker = ?,
                    sold_to = ?,
                    deliver_to = ?,
                    received_by = ?,
                    gross_weight = ?,
                    tare_weight = ?,
                    net_weight = ?,
                    source_site = ?,
                    destination_site = ?,
                    review_status = 'approved',
                    reviewed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                params,
            )
    logger.info("ticket_approved row_id=%s ticket_id=%s", ticket_row_id, edited.get("ticket_id", ""))
    return None


def reject_ticket(ticket_row_id: int, reviewer: str) -> None:
    now = dt.datetime.utcnow().isoformat()
    with get_conn() as conn:
        params = (reviewer, now, now, ticket_row_id)
        if postgres_enabled():
            conn.execute(
                """
                UPDATE tickets
                SET review_status = 'rejected',
                    reviewed_by = %s,
                    reviewed_at = %s,
                    updated_at = %s
                WHERE id = %s
                """,
                params,
            )
        else:
            conn.execute(
                """
                UPDATE tickets
                SET review_status = 'rejected',
                    reviewed_by = ?,
                    reviewed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                params,
            )
    logger.info("ticket_rejected row_id=%s reviewer=%s", ticket_row_id, reviewer)


def export_approved_to_csv() -> Optional[Path]:
    with get_conn() as conn:
        if postgres_enabled():
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                """
                SELECT * FROM tickets
                WHERE review_status = 'approved'
                  AND exported_at IS NULL
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()
        else:
            cursor = conn.execute(
                """
                SELECT * FROM tickets
                WHERE review_status = 'approved'
                  AND exported_at IS NULL
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()

        if not rows:
            return None

        file_name = f"ticket_export_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        out_path = EXPORT_DIR / file_name

        csv_headers = [
            "Customer",
            "Ticket Date",
            "Quarry",
            "Product Name",
            "Ticket Number",
            "Gross",
            "Tare",
            "Net",
            "Delivery",
            "Purchase Order",
            "Trucker",
            "Truck / Plate",
            "OCR Provider",
            "Captured At",
        ]
        db_fields = [
            "sold_to",
            "ticket_date",
            "quarry_name",
            "material_type",
            "ticket_id",
            "gross_weight",
            "tare_weight",
            "net_weight",
            "deliver_to",
            "job_no",
            "trucker",
            "truck_or_plate",
            "ocr_provider",
            "created_at",
        ]

        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(csv_headers)
            for row in rows:
                writer.writerow([row[field] for field in db_fields])

        if bucket_enabled():
            upload_to_bucket(out_path, "exports")

        now = dt.datetime.utcnow().isoformat()
        ids = [row["id"] for row in rows]
        if postgres_enabled():
            batch_cursor = conn.cursor()
            batch_cursor.execute(
                """
                INSERT INTO export_batches (file_name, exported_at, ticket_count)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (file_name, now, len(rows)),
            )
            batch_id = batch_cursor.fetchone()[0]
            conn.execute(
                f"UPDATE tickets SET exported_at = %s, export_batch_id = %s, updated_at = %s WHERE id IN ({_db_param_placeholder_count(len(ids))})",
                [now, batch_id, now, *ids],
            )
        else:
            batch_cursor = conn.execute(
                """
                INSERT INTO export_batches (file_name, exported_at, ticket_count)
                VALUES (?, ?, ?)
                """,
                (file_name, now, len(rows)),
            )
            batch_id = batch_cursor.lastrowid
            placeholders = _db_param_placeholder_count(len(ids))
            conn.execute(
                f"UPDATE tickets SET exported_at = ?, export_batch_id = ?, updated_at = ? WHERE id IN ({placeholders})",
                [now, batch_id, now, *ids],
            )

    return out_path


def _clean_num_str(val: Any) -> str:
    if val is None:
        return ""
    return re.sub(r"[^\d]", "", str(val))


def validate_required(data: Dict[str, str]) -> List[str]:
    errors = []
    field_labels = {
        "ticket_id": "Ticket Number",
        "ticket_date": "Date",
        "quarry_name": "Quarry Name",
        "sold_to": "Customer (Sold To)",
        "material_type": "Material",
        "gross_weight": "Gross Weight",
        "tare_weight": "Tare Weight",
        "net_weight": "Net Weight",
    }
    for field in REQUIRED_FIELDS:
        if not str(data.get(field, "")).strip():
            label = field_labels.get(field, field.replace("_", " ").title())
            errors.append(f"'{label}' is required before approving.")

    for numeric in ["gross_weight", "tare_weight", "net_weight"]:
        raw = str(data.get(numeric, "")).strip()
        if raw and not _clean_num_str(raw):
            label = field_labels.get(numeric, numeric.replace("_", " ").title())
            errors.append(f"'{label}' must be a valid number.")

    return errors


def validate_deliver_to_quality(value: str) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None

    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    if not tokens:
        return "Deliver To looks unreadable. Verify against the ticket image."

    road_suffixes = {
        "rd", "road", "st", "street", "ave", "avenue", "dr", "drive", "ln", "lane", "blvd", "boulevard", "hwy", "highway",
    }
    has_number = any(any(ch.isdigit() for ch in token) for token in tokens)

    if len(tokens) == 1 and len(tokens[0]) >= 3:
        return "Deliver To appears incomplete (single token). Verify full destination."

    if len(tokens) <= 2 and not has_number and tokens[-1] in road_suffixes:
        return "Deliver To appears incomplete (road-only fragment). Verify full destination."

    if len(text) < 8 and not has_number:
        return "Deliver To appears too short. Verify full destination."

    return None


def render_upload_tab() -> None:
    st.subheader("1) Upload + OCR")
    provider = os.getenv("OCR_PROVIDER", "").strip().lower()
    if provider == "google_vision":
        st.info(
            "Production mode: Google Vision OCR is active. This path can incur Google Cloud billing after the free tier is exhausted."
        )
        st.caption(
            "Confidence shown per ticket is the average word-level score "
            "Google Vision returns — high-quality photos typically score 85\u201395%."
        )
    else:
        st.success(
            "Demo mode: pytesseract OCR is active. This path is local and does not incur Google billing."
        )
        st.caption(
            "Confidence is fixed at 55% for Tesseract — it does not produce per-word scores. "
            "Use OCR_PROVIDER=google_vision only for a paid Google Cloud setup."
        )
    uploaded = st.file_uploader(
        "Upload ticket images",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
    )

    if st.button("Process Uploads", type="primary"):
        if not uploaded:
            st.warning("Upload at least one file.")
            return

        processed_count = 0
        for file in uploaded:
            try:
                file_bytes = file.getbuffer()
                timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
                file_path = UPLOAD_DIR / f"{timestamp}_{file.name}"
                file_path.write_bytes(file_bytes)
                logger.info("upload_saved file=%s size_bytes=%s path=%s", file.name, len(file_bytes), file_path)

                # PDF Multi-page Ticket Batch Handling
                if file.name.lower().endswith(".pdf"):
                    try:
                        import pypdf
                        reader = pypdf.PdfReader(file_path)
                        pdf_pages_ingested = 0
                        for page_idx, page in enumerate(reader.pages):
                            if page.images:
                                for img_idx, img in enumerate(page.images):
                                    page_img_name = f"{timestamp}_p{page_idx+1}_{img_idx+1}_{file.name.rsplit('.', 1)[0]}.jpg"
                                    page_img_path = UPLOAD_DIR / page_img_name
                                    page_img_path.write_bytes(img.data)

                                    fields, confidence, provider_used = extract_ticket_data(page_img_path)
                                    raw_ocr_text = fields.pop("__raw_text", "")
                                    fields.pop("__ocr_warning", None)
                                    stored_page_reference = persist_file(page_img_path, "uploads")
                                    insert_ticket(fields, confidence, stored_page_reference, provider_used, raw_ocr_text)
                                    pdf_pages_ingested += 1
                                    processed_count += 1
                        if pdf_pages_ingested > 0:
                            st.success(f"Extracted and queued {pdf_pages_ingested} ticket page(s) from '{file.name}'.")
                            continue
                    except Exception as pdf_exc:
                        logger.warning("pdf_extraction_failed file=%s error=%s", file.name, pdf_exc)

                fields, confidence, provider_used = extract_ticket_data(file_path)
                raw_ocr_text = fields.pop("__raw_text", "")
                fields.pop("__ocr_warning", None)  # handled below

                logger.info(
                    "upload_processed file=%s provider=%s confidence=%.2f ticket_id=%s",
                    file.name, provider_used, confidence, fields.get("ticket_id", ""),
                )

                warning_msg = str(fields.get("__ocr_warning", "")).strip()
                if warning_msg:
                    logger.warning("upload_ocr_warning file=%s warning=%s", file.name, warning_msg)
                    st.warning(f"{file.name}: {warning_msg}")

                stored_file_reference = persist_file(file_path, "uploads")
                insert_ticket(fields, confidence, stored_file_reference, provider_used, raw_ocr_text)
                processed_count += 1
            except Exception as exc:
                logger.exception("upload_processing_failed file=%s error=%s", file.name, exc)
                st.error(f"Failed to process {file.name}. Check backend log for details.")

        st.success(f"Successfully processed and queued {processed_count} ticket item(s).")


def render_review_tab() -> None:
    st.subheader("2) Review Queue")

    pending = fetch_tickets(["needs_review", "auto_ready"])
    if not pending:
        st.info("No tickets in review queue.")
        return

    # ── Reviewer + ticket selector ─────────────────────────────────────────────
    reviewer = st.text_input("Reviewer name", value="office", key="reviewer_name")

    def _format_ticket_option(r: sqlite3.Row) -> str:
        t_num = r["ticket_id"] or "Unread Ticket #"
        t_date = r["ticket_date"] or "No Date"
        quarry = r["quarry_name"] or "Quarry Unread"
        conf = f"{r['confidence_score']:.0%}"
        captured = sum(1 for f in REQUIRED_FIELDS if str(r[f] or "").strip())
        total = len(REQUIRED_FIELDS)
        return (
            f"Ticket #{t_num} — {t_date} (Quarry: {quarry} | "
            f"Text Clarity: {conf} | Fields Captured: {captured}/{total})"
        )

    options = {
        _format_ticket_option(row): row["id"]
        for row in pending
    }
    selected_label = st.selectbox("Select ticket to review", list(options.keys()))

    if not duplicates_check_enabled():
        st.caption("Duplicate check disabled (testing mode)")

    selected_id = options[selected_label]
    row = fetch_ticket(selected_id)
    if not row:
        st.error("Ticket not found.")
        return

    # ── Pre-flight validation ──────────────────────────────────────────────────
    gross_raw = str(row["gross_weight"] or "").strip()
    tare_raw  = str(row["tare_weight"]  or "").strip()
    net_raw   = str(row["net_weight"]   or "").strip()

    gross_clean = _clean_num_str(gross_raw)
    tare_clean  = _clean_num_str(tare_raw)
    net_clean   = _clean_num_str(net_raw)

    issues: List[str] = []
    calc_net: Optional[int] = None

    if gross_clean and tare_clean:
        calc_net = int(gross_clean) - int(tare_clean)
        if net_clean:
            if abs(calc_net - int(net_clean)) > 10:
                issues.append(f"Net mismatch — ticket shows **{net_raw}** but Gross−Tare calculates to **{calc_net:,}**")
        else:
            issues.append(f"Net weight empty — calculated value from Gross−Tare = **{calc_net:,}**")
    elif not gross_clean or not tare_clean:
        issues.append("Gross and/or Tare not captured — cannot verify net")

    missing_required = [f for f in REQUIRED_FIELDS if not str(row[f] or "").strip()]
    field_names = {
        "ticket_id": "Ticket Number",
        "ticket_date": "Date",
        "quarry_name": "Quarry Name",
        "sold_to": "Customer (Sold To)",
        "material_type": "Material",
        "gross_weight": "Gross Weight",
        "tare_weight": "Tare Weight",
        "net_weight": "Net Weight",
    }
    for f in missing_required:
        label = field_names.get(f, f.replace('_', ' ').title())
        issues.append(f"**{label}** — not captured by OCR")

    deliver_to_issue = validate_deliver_to_quality(str(row["deliver_to"] or ""))
    if deliver_to_issue:
        issues.append(deliver_to_issue)

    if duplicates_check_enabled() and row["ticket_id"]:
        with get_conn() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE ticket_id = ? AND id != ? AND review_status != 'rejected'",
                (row["ticket_id"], selected_id),
            )
            if cur.fetchone()[0] > 0:
                issues.append(f"Possible duplicate — Ticket #{row['ticket_id']} already exists")

    if issues:
        with st.expander(f"{len(issues)} issue(s) — verify before saving", expanded=True):
            for issue in issues:
                st.markdown(f"- {issue}")
    else:
        st.success("All required fields captured and weights verified")

    st.divider()

    # ── Main layout: image | form ──────────────────────────────────────────────
    img_col, form_col = st.columns([1, 1])
    edited: Dict[str, str] = {}

    with img_col:
        image_bytes = load_stored_file(row["image_path"])
        if image_bytes:
            st.image(image_bytes, use_column_width=True)
        else:
            st.warning("Ticket image could not be loaded from storage.")

        # Raw OCR text viewer (collapsible)
        raw_text = row["raw_ocr_text"] if "raw_ocr_text" in row.keys() else ""
        if raw_text:
            with st.expander("Raw OCR text (use to fill missing fields)", expanded=False):
                st.code(raw_text, language="text")

    with form_col:
        with st.form(f"review_form_{selected_id}"):
            st.markdown("**Identity**")
            c1, c2 = st.columns(2)
            with c1:
                edited["ticket_id"]   = st.text_input("Ticket No.", value=row["ticket_id"] or "")
                edited["ticket_date"] = st.text_input("Date (YYYY-MM-DD)", value=row["ticket_date"] or "")
                edited["job_no"]      = st.text_input("Job No.", value=row["job_no"] or "")
            with c2:
                known_quarries = [
                    "Seabrook", "Desmond", "Long Point", "Pleasant Valley",
                    "Shelburne", "Brierly Brook", "Cochrane Hill", "Middlewood",
                    "Westchester", "Larry J Beck"
                ]
                q_default = row["quarry_name"] if row["quarry_name"] in known_quarries else "Long Point"
                q_idx = known_quarries.index(q_default) if q_default in known_quarries else 0
                edited["quarry_name"]   = st.selectbox("Quarry", known_quarries, index=q_idx)
                edited["sold_to"]       = st.text_input("Customer (Sold To)", value=row["sold_to"] or "")
                edited["material_type"] = st.text_input("Material", value=row["material_type"] or "")

            st.markdown("**Weights**")
            w1, w2, w3 = st.columns(3)
            with w1:
                edited["gross_weight"] = st.text_input("Gross", value=gross_raw)
            with w2:
                edited["tare_weight"]  = st.text_input("Tare",  value=tare_raw)
            with w3:
                default_net = net_raw or (str(calc_net) if calc_net is not None else "")
                edited["net_weight"]   = st.text_input("Net",   value=default_net)
            if calc_net is not None:
                st.caption(f"Calculated net (Gross − Tare) = **{calc_net:,}**")

            st.markdown("**Transport**")
            t1, t2 = st.columns(2)
            with t1:
                edited["truck_or_plate"] = st.text_input("Truck / Plate", value=row["truck_or_plate"] or "")
                edited["trucker"]        = st.text_input("Trucker", value=row["trucker"] or "")
            with t2:
                edited["deliver_to"]  = st.text_input("Deliver To", value=row["deliver_to"] or "")
                edited["received_by"] = st.text_input("Received By", value=row["received_by"] or "")

            save_clicked   = st.form_submit_button("Save & Approve", type="primary")
            reject_clicked = st.form_submit_button("Reject")

        # ── Save / reject logic ─────────────────────────────────────────────
        # Rendered inside form_col (right below the buttons) instead of full
        # width below both columns, so the reviewer doesn't have to scroll
        # down to see whether their approval succeeded or failed.
        if save_clicked:
            errors = validate_required(edited)
            deliver_to_issue = validate_deliver_to_quality(edited.get("deliver_to", ""))
            if deliver_to_issue:
                errors.append(deliver_to_issue)
            g_clean = _clean_num_str(edited.get("gross_weight", ""))
            t_clean = _clean_num_str(edited.get("tare_weight",  ""))
            n_clean = _clean_num_str(edited.get("net_weight",   ""))
            if g_clean and t_clean and n_clean:
                expected = int(g_clean) - int(t_clean)
                if abs(expected - int(n_clean)) > 10:
                    errors.append(
                        f"Net mismatch: Gross ({int(g_clean):,}) − Tare ({int(t_clean):,}) = {expected:,}, but entered Net is {edited.get('net_weight')}. "
                        "Correct Net or verify against the ticket image."
                    )
            if errors:
                for err in errors:
                    st.error(err)
            else:
                err_msg = approve_ticket(selected_id, edited)
                if err_msg:
                    st.error(err_msg)
                else:
                    st.success(f"Ticket #{edited['ticket_id']} approved.")
                    st.rerun()

        if reject_clicked:
            reject_ticket(selected_id, reviewer)
            st.warning(f"Ticket #{row['ticket_id'] or selected_id} rejected.")
            st.rerun()


def render_export_tab() -> None:
    st.subheader("3) Approved + Export")

    approved = fetch_tickets(["approved"])
    st.caption(f"{len(approved)} approved ticket(s) ready")

    if approved:
        st.dataframe(
            [
                {
                    "id":        row["id"],
                    "Ticket #":  row["ticket_id"],
                    "Date":      row["ticket_date"],
                    "Quarry":    row["quarry_name"],
                    "Customer":  row["sold_to"],
                    "Material":  row["material_type"],
                    "Gross":     row["gross_weight"],
                    "Tare":      row["tare_weight"],
                    "Net":       row["net_weight"],
                    "Provider":  row["ocr_provider"],
                    "Exported":  row["exported_at"] or "—",
                }
                for row in approved
            ],
            use_container_width=True,
        )

    if st.button("Export approved tickets to CSV", type="primary"):
        out_path = export_approved_to_csv()
        if not out_path:
            st.info("No unexported approved tickets available.")
        else:
            st.success(f"Exported to {out_path}")


def render_history_tab() -> None:
    st.subheader("5) Ticket History")
    completed = fetch_tickets(["approved", "rejected"])
    if not completed:
        st.info("No processed tickets yet.")
        return

    options = {
        f"#{row['id']} | {row['ticket_id'] or 'No ticket number'} | "
        f"{row['ticket_date'] or 'No date'} | {row['review_status']} | "
        f"{'exported' if row['exported_at'] else 'not exported'}": row["id"]
        for row in completed
    }
    selected_id = options[st.selectbox("Select processed ticket", list(options.keys()))]
    row = fetch_ticket(selected_id)
    if not row:
        st.error("Ticket not found.")
        return

    image_col, details_col = st.columns([1, 1])
    with image_col:
        image_bytes = load_stored_file(row["image_path"])
        if image_bytes:
            st.image(image_bytes, use_column_width=True)
        else:
            st.warning("Ticket image could not be loaded from storage.")
    with details_col:
        st.caption(f"Status: {row['review_status']} | Exported: {row['exported_at'] or 'No'}")
        st.dataframe(
            [{
                "Ticket #": row["ticket_id"], "Date": row["ticket_date"],
                "Customer": row["sold_to"], "Quarry": row["quarry_name"],
                "Material": row["material_type"], "Gross": row["gross_weight"],
                "Tare": row["tare_weight"], "Net": row["net_weight"],
            }],
            use_container_width=True,
            hide_index=True,
        )
        st.warning("Reopening sends this ticket back to Review and removes it from any previous export batch.")
        if st.button("Reopen for correction", type="primary", key=f"reopen_ticket_{selected_id}"):
            reopen_ticket_for_correction(selected_id)
            st.success("Ticket reopened. Use the Review tab to make corrections and approve it again.")
            st.rerun()

        replacement = st.file_uploader(
            "Replace ticket image and re-run review",
            type=["png", "jpg", "jpeg", "pdf"],
            key=f"replacement_image_{selected_id}",
        )
        if replacement and st.button("Use replacement image", key=f"replace_image_{selected_id}"):
            timestamp = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            new_path = UPLOAD_DIR / f"{timestamp}_{replacement.name}"
            new_path.write_bytes(replacement.getbuffer())
            reopen_ticket_for_correction(selected_id, str(new_path))
            st.success("Replacement image saved. Ticket reopened for review.")
            st.rerun()

    st.divider()
    st.subheader("Export Batch Archive")
    batches = fetch_export_batches()
    if not batches:
        st.info("No export batches have been created since batch archiving was enabled.")
        return

    batch_options = {
        f"Batch #{batch['id']} | {batch['file_name']} | {batch['ticket_count']} ticket(s) | {batch['exported_at']}": batch["id"]
        for batch in batches
    }
    selected_batch_id = batch_options[st.selectbox("Select past export", list(batch_options.keys()))]
    batch_tickets = fetch_export_batch_tickets(selected_batch_id)
    if batch_tickets:
        st.dataframe(
            [{"Ticket #": ticket["ticket_id"], "Date": ticket["ticket_date"], "Customer": ticket["sold_to"], "Net": ticket["net_weight"]} for ticket in batch_tickets],
            use_container_width=True,
            hide_index=True,
        )
        if st.button("Return batch to export queue", key=f"reopen_batch_{selected_batch_id}"):
            count = reopen_export_batch(selected_batch_id)
            st.success(f"Returned {count} ticket(s) to the export queue.")
            st.rerun()
    else:
        st.info("This batch has already been returned to the export queue.")


def render_status_tab() -> None:
    st.subheader("4) Status & Admin")
    all_rows = fetch_tickets()

    if not all_rows:
        st.info("No tickets yet.")
    else:
        # Summary table
        counts: Dict[str, int] = {}
        for row in all_rows:
            counts[row["review_status"]] = counts.get(row["review_status"], 0) + 1

        summary_rows = [
            {"Status": k, "Count": v, "%": f"{v / len(all_rows):.0%}"}
            for k, v in sorted(counts.items())
        ]
        st.dataframe(summary_rows, use_container_width=True, hide_index=True)

        # Provider breakdown
        provider_counts: Dict[str, int] = {}
        for row in all_rows:
            p = row["ocr_provider"]
            provider_counts[p] = provider_counts.get(p, 0) + 1
        st.caption("By OCR provider: " + "  |  ".join(f"{k}: {v}" for k, v in provider_counts.items()))

    # ── Data management ───────────────────────────────────────────────────────
    st.divider()
    st.subheader("Data Management")
    dm_col1, dm_col2, dm_col3 = st.columns(3)
    with dm_col1:
        if st.button("Clear unreviewed (test cleanup)", help="Deletes needs_review and auto_ready tickets"):
            with get_conn() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM tickets WHERE review_status IN ('needs_review','auto_ready')"
                ).fetchone()[0]
                conn.execute("DELETE FROM tickets WHERE review_status IN ('needs_review','auto_ready')")
            logger.info("admin_clear_unreviewed deleted=%d", n)
            st.success(f"Deleted {n} unreviewed ticket(s).")
            st.rerun()
    with dm_col2:
        if st.button("Clear rejected", help="Deletes all rejected tickets"):
            with get_conn() as conn:
                n = conn.execute(
                    "SELECT COUNT(*) FROM tickets WHERE review_status = 'rejected'"
                ).fetchone()[0]
                conn.execute("DELETE FROM tickets WHERE review_status = 'rejected'")
            logger.info("admin_clear_rejected deleted=%d", n)
            st.success(f"Deleted {n} rejected ticket(s).")
            st.rerun()
    with dm_col3:
        if st.button("Reset unexported flag", help="Marks all approved tickets as not yet exported"):
            with get_conn() as conn:
                conn.execute(
                    """
                    UPDATE tickets
                    SET exported_at = NULL, export_batch_id = NULL
                    WHERE review_status = 'approved'
                    """
                )
            st.success("Export flag reset.")
            st.rerun()

    # ── Backend log viewer ─────────────────────────────────────────────────────
    st.divider()
    log_path = get_log_path()
    st.caption(f"Log file: {log_path}")
    with st.expander("Backend log (latest 200 lines)", expanded=False):
        log_text = tail_log_lines(200)
        st.code(log_text or "No backend logs yet.", language="text")


def main() -> None:
    st.set_page_config(
        page_title="Nova Construction — Ticket Processing",
        layout="wide",
        menu_items={"Get Help": None, "Report a bug": None, "About": None},
    )

    ensure_paths()
    init_db()
    logger.info(
        "app_start provider_env=%s duplicate_check_enabled=%s",
        os.getenv("OCR_PROVIDER", "").strip().lower() or "<empty>",
        duplicates_check_enabled(),
    )

    # ── Theme: read from URL param, default dark ──────────────────────────────
    raw_param = st.query_params.get("theme", "dark").lower()
    theme = "light" if raw_param == "light" else "dark"

    is_dark   = (theme == "dark")
    icon      = "\u2600" if is_dark else "\u263d"   # ☀ / ☽  (text glyphs, not emoji)
    next_mode = "light"  if is_dark else "dark"
    tip       = "Switch to Light Mode" if is_dark else "Switch to Dark Mode"

    # ── Fixed-position sun/moon button near the Deploy button ─────────────────
    btn_color = "#FFFFFF" if is_dark else "#1F2937"
    btn_border = "rgba(217,64,53,0.55)" if is_dark else "rgba(191,27,27,0.4)"
    btn_bg     = "rgba(217,64,53,0.12)" if is_dark else "rgba(191,27,27,0.07)"
    btn_hover  = "rgba(217,64,53,0.28)" if is_dark else "rgba(191,27,27,0.18)"
    st.markdown(f"""
<style>
.nc-theme-btn {{
    position: fixed !important;
    top: 0.6rem;
    right: 7.5rem;
    z-index: 99999;
    font-size: 1.2rem;
    line-height: 1;
    text-decoration: none;
    background: {btn_bg};
    border: 1px solid {btn_border};
    padding: 0.22rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    color: {btn_color} !important;
    transition: background 0.15s, border-color 0.15s;
    font-style: normal;
}}
.nc-theme-btn:hover {{ background: {btn_hover}; border-color: #D94035; }}
</style>
<a class="nc-theme-btn" href="?theme={next_mode}" title="{tip}">{icon}</a>
""", unsafe_allow_html=True)

    # ── Common brand CSS (always applied on top of config.toml dark base) ─────
    st.markdown("""
<style>
/* Primary buttons — Nova red */
[data-testid="baseButton-primary"] {
    background-color: #D94035 !important;
    border-color:     #D94035 !important;
    font-weight: 500 !important;
}
[data-testid="baseButton-primary"]:hover {
    background-color: #B83029 !important;
    border-color:     #B83029 !important;
}
/* Selected tab indicator */
.stTabs [aria-selected="true"] {
    color: #D94035 !important;
    border-bottom-color: #D94035 !important;
    font-weight: 600 !important;
}
h1 { font-weight: 700 !important; letter-spacing: -0.01em !important; }
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

    # ── Light-mode full override ───────────────────────────────────────────────
    if not is_dark:
        st.markdown("""
<style>
/* ─── Light Mode Override (Nova Construction brand) ──────────────────── */
[data-testid="stApp"],
.main,
[data-testid="stAppViewContainer"],
[data-testid="block-container"],
[data-testid="stMainBlockContainer"] {
    background-color: #FFFFFF !important;
    color: #111827 !important;
}
[data-testid="stHeader"] {
    background-color: #FFFFFF !important;
    border-bottom: 1px solid #E5E7EB !important;
}
/* Widget and form surfaces */
[data-testid="stForm"] {
    background-color: #F9FAFB !important;
    border-color: #E5E7EB !important;
}
section.main > div, [data-testid="stVerticalBlockBorderWrapper"] > div {
    background-color: #F9FAFB !important;
    border-color: #E5E7EB !important;
}
/* Text inputs */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
    background-color: #FFFFFF !important;
    color: #111827 !important;
    border-color: #D1D5DB !important;
}
/* Selectbox */
[data-baseweb="select"] > div {
    background-color: #FFFFFF !important;
    color: #111827 !important;
    border-color: #D1D5DB !important;
}
[data-baseweb="popover"] ul, [data-baseweb="menu"] {
    background-color: #FFFFFF !important;
}
[data-baseweb="option"] {
    background-color: #FFFFFF !important;
    color: #111827 !important;
}
[data-baseweb="option"]:hover { background-color: #F3F4F6 !important; }
/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background-color: #FFFFFF !important;
    border-bottom-color: #E5E7EB !important;
}
.stTabs [role="tab"] { color: #6B7280 !important; }
.stTabs [aria-selected="true"] {
    color: #BF1B1B !important;
    border-bottom-color: #BF1B1B !important;
}
/* Primary button override for light */
[data-testid="baseButton-primary"] {
    background-color: #BF1B1B !important;
    border-color:     #BF1B1B !important;
}
[data-testid="baseButton-primary"]:hover {
    background-color: #9C1515 !important;
    border-color:     #9C1515 !important;
}
/* Secondary buttons */
[data-testid="baseButton-secondary"] {
    color: #111827 !important;
    border-color: #D1D5DB !important;
    background-color: #FFFFFF !important;
}
/* Text and headings */
p, label, h1, h2, h3, h4, strong,
[data-testid="stMarkdown"], [data-testid="stText"] { color: #111827 !important; }
[data-testid="stCaptionContainer"] { color: #6B7280 !important; }
/* Expanders */
.streamlit-expanderHeader {
    color: #111827 !important;
    background-color: #F9FAFB !important;
}
.streamlit-expanderContent {
    background-color: #FFFFFF !important;
    border-color: #E5E7EB !important;
}
/* Alerts */
[data-testid="stAlert"] {
    background-color: rgba(0,0,0,0.04) !important;
    color: #111827 !important;
}
/* Code block */
[data-testid="stCode"] pre {
    background-color: #F3F4F6 !important;
    color: #1F2937 !important;
    border: 1px solid #E5E7EB !important;
}
/* File uploader */
[data-testid="stFileUploader"] {
    background-color: #F9FAFB !important;
    border-color: #D1D5DB !important;
    color: #111827 !important;
}
[data-testid="stFileUploaderDropzone"] {
    background-color: #F9FAFB !important;
}
/* Dataframe wrapper */
[data-testid="stDataFrame"] {
    background-color: #FFFFFF !important;
}
hr { border-color: #E5E7EB !important; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #F3F4F6; }
::-webkit-scrollbar-thumb { background: #D1D5DB; border-radius: 3px; }
.nc-theme-btn { color: #374151 !important; }
</style>
""", unsafe_allow_html=True)

    # ── Page content ──────────────────────────────────────────────────────────
    st.title("Nova Construction — Ticket Processing System")
    st.caption("Step 1: Upload Photos  \u2192  Step 2: Review & Confirm  \u2192  Step 3: Export for Invoicing")
    st.divider()

    tabs = st.tabs(["1. Upload Tickets", "2. Review & Approve", "3. Exported Tickets", "4. Ticket History", "5. System Admin"])

    with tabs[0]:
        render_upload_tab()
    with tabs[1]:
        render_review_tab()
    with tabs[2]:
        render_export_tab()
    with tabs[3]:
        render_history_tab()
    with tabs[4]:
        render_status_tab()


if __name__ == "__main__":
    main()
