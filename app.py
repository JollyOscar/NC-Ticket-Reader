import csv
import datetime as dt
import hmac
import json
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
MASTER_DATA_PATH = Path(os.getenv("MASTER_DATA_PATH", str(BASE_DIR / "master_data.csv")))

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


def _normalize_lookup_value(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


@st.cache_data(ttl=300)
def load_master_data() -> Dict[str, Dict[str, str]]:
    lookups: Dict[str, Dict[str, str]] = {"customer": {}, "quarry": {}, "material": {}}
    if not MASTER_DATA_PATH.exists():
        return lookups

    with MASTER_DATA_PATH.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            entity_type = str(row.get("entity_type", "")).strip().lower()
            name = str(row.get("name", "")).strip()
            system_id = str(row.get("system_id", "")).strip()
            aliases = str(row.get("aliases", "")).split("|")
            if entity_type not in lookups or not name or not system_id:
                continue
            for candidate in [name, *aliases]:
                normalized = _normalize_lookup_value(candidate)
                if normalized:
                    lookups[entity_type][normalized] = system_id
    return lookups


def lookup_system_id(entity_type: str, value: str, lookups: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    source = lookups if lookups is not None else load_master_data()
    norm = _normalize_lookup_value(value)
    found = source.get(entity_type, {}).get(norm, "")
    if found:
        return found
    if entity_type == "material" and value:
        val_lower = str(value).lower()
        if any(w in val_lower for w in ("asphalt", "mix", "hma", "binder", "tack", "shim", "paving", "rap", "millings")):
            return "21"
        return "20"
    return ""


@st.cache_data(ttl=300)
def get_master_data_canonical_names() -> Dict[str, List[str]]:
    names: Dict[str, List[str]] = {"customer": [], "quarry": [], "material": []}
    if not MASTER_DATA_PATH.exists():
        return names
    with MASTER_DATA_PATH.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            entity_type = str(row.get("entity_type", "")).strip().lower()
            name = str(row.get("name", "")).strip()
            if entity_type in names and name and name not in names[entity_type]:
                names[entity_type].append(name)
    return names


@st.cache_data(ttl=300)
def get_master_data_id_map() -> Dict[str, Dict[str, str]]:
    id_map: Dict[str, Dict[str, str]] = {"customer": {}, "quarry": {}, "material": {}}
    if not MASTER_DATA_PATH.exists():
        return id_map
    with MASTER_DATA_PATH.open(newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            entity_type = str(row.get("entity_type", "")).strip().lower()
            name = str(row.get("name", "")).strip()
            system_id = str(row.get("system_id", "")).strip()
            if entity_type in id_map and name and system_id and system_id not in id_map[entity_type]:
                id_map[entity_type][system_id] = name
    return id_map


@st.cache_data(ttl=300)
def match_master_entity(entity_type: str, raw_text: str) -> Tuple[str, str]:
    """Fuzzy/token match raw text to canonical master data name and system ID."""
    import difflib

    raw_str = str(raw_text or "").strip()
    if not raw_str:
        return ("", "")

    lookups = load_master_data()
    norm_input = _normalize_lookup_value(raw_str)
    canonical_names = get_master_data_canonical_names().get(entity_type, [])
    id_map = get_master_data_id_map().get(entity_type, {})

    # 1. Direct exact / normalized match (O(1))
    direct_id = lookup_system_id(entity_type, raw_str, lookups)
    if direct_id:
        canonical_name = id_map.get(direct_id)
        if canonical_name:
            return (canonical_name, direct_id)

    # 2. Token / Substring / Fuzzy match
    if not canonical_names or len(norm_input) < 2:
        return (raw_str, direct_id)

    best_candidate = ""
    best_score = 0.0
    best_sys_id = ""

    for canonical_name in canonical_names:
        sys_id = id_map.get(canonical_name) or lookup_system_id(entity_type, canonical_name, lookups)
        norm_canonical = _normalize_lookup_value(canonical_name)

        if norm_input and norm_canonical.startswith(norm_input):
            score = 0.85 + (len(norm_input) / float(len(norm_canonical)) * 0.1)
            if score > best_score:
                best_score = score
                best_candidate = canonical_name
                best_sys_id = sys_id
        elif norm_input and norm_input in norm_canonical:
            score = 0.60 + (len(norm_input) / float(len(norm_canonical)) * 0.2)
            if score > best_score:
                best_score = score
                best_candidate = canonical_name
                best_sys_id = sys_id

        ratio = difflib.SequenceMatcher(None, norm_input, norm_canonical).ratio()
        if ratio > 0.65 and ratio > best_score:
            best_score = ratio
            best_candidate = canonical_name
            best_sys_id = sys_id

    if best_candidate and best_score >= 0.50:
        return (best_candidate, best_sys_id)

    return (raw_str, direct_id)


def format_export_date(value: str) -> str:
    raw_date = str(value or "").strip()
    if not raw_date:
        return ""
    # Try standard ISO format YYYY-MM-DD
    try:
        parsed = dt.date.fromisoformat(raw_date)
        return parsed.strftime(os.getenv("NETSUITE_DATE_FORMAT", "%m/%d/%Y"))
    except ValueError:
        pass

    # Try common alternate date formats
    for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y.%m.%d", "%d-%m-%Y", "%m-%d-%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            parsed = dt.datetime.strptime(raw_date, fmt).date()
            return parsed.strftime(os.getenv("NETSUITE_DATE_FORMAT", "%m/%d/%Y"))
        except ValueError:
            pass

    return raw_date


def current_actor() -> str:
    return str(st.session_state.get("authenticated_actor", "unsecured"))


def configured_user_credentials() -> Dict[str, str]:
    raw = os.getenv("APP_USER_CREDENTIALS", "").strip()
    if not raw:
        return {}
    try:
        values = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("app_user_credentials_invalid_json")
        return {}
    if not isinstance(values, dict):
        return {}
    return {
        str(name).strip(): str(password)
        for name, password in values.items()
        if str(name).strip() and isinstance(password, str)
    }


def require_authenticated_actor() -> str:
    password = os.getenv("APP_ACCESS_PASSWORD", "")
    credentials = configured_user_credentials()
    if not password and not credentials:
        return "unsecured"

    actor = current_actor()
    if actor != "unsecured":
        return actor

    st.title("Nova Construction Ticket Processing")
    st.caption("Sign in to access ticket records.")
    with st.form("sign_in"):
        name = st.text_input("Name")
        entered_password = st.text_input("Password", type="password")
        sign_in = st.form_submit_button("Sign in", type="primary")
    if sign_in:
        allowed_names = {
            item.strip().lower()
            for item in os.getenv("APP_ALLOWED_USERS", "").split(",")
            if item.strip()
        }
        expected_password = credentials.get(name.strip(), "") if credentials else password
        valid_name = bool(name.strip()) and bool(expected_password) and (
            bool(credentials) or not allowed_names or name.strip().lower() in allowed_names
        )
        if valid_name and hmac.compare_digest(entered_password, expected_password):
            st.session_state["authenticated_actor"] = name.strip()
            st.rerun()
        st.error("Invalid name or password.")
    st.stop()
    return ""


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


@st.cache_data(ttl=600, max_entries=200)
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
                    created_by TEXT,
                    customer_id TEXT,
                    quarry_id TEXT,
                    material_id TEXT,
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
                    ticket_count INTEGER NOT NULL,
                    exported_by TEXT
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
                    created_by TEXT,
                    customer_id TEXT,
                    quarry_id TEXT,
                    material_id TEXT,
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
                    ticket_count INTEGER NOT NULL,
                    exported_by TEXT
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
            "created_by": "TEXT",
            "customer_id": "TEXT",
            "quarry_id": "TEXT",
            "material_id": "TEXT",
        }
        for col, col_type in maybe_add.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE tickets ADD COLUMN {col} {col_type}")

        if postgres_enabled():
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'export_batches'"
            )
            batch_columns = {row[0] for row in cursor.fetchall()}
        else:
            cursor = conn.execute("PRAGMA table_info(export_batches)")
            batch_columns = {row[1] for row in cursor.fetchall()}
        if "exported_by" not in batch_columns:
            conn.execute("ALTER TABLE export_batches ADD COLUMN exported_by TEXT")


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


def insert_ticket(fields: Dict[str, str], confidence_score: float, image_path: str, ocr_provider: str, raw_ocr_text: str = "", actor: str = "unsecured") -> None:
    status = "auto_ready" if confidence_score >= 0.85 else "needs_review"
    now = dt.datetime.utcnow().isoformat()

    # Apply fuzzy master data resolution to extracted fields
    if fields.get("sold_to"):
        c_name, _ = match_master_entity("customer", fields["sold_to"])
        if c_name:
            fields["sold_to"] = c_name

    if fields.get("quarry_name"):
        q_name, _ = match_master_entity("quarry", fields["quarry_name"])
        if q_name:
            fields["quarry_name"] = q_name

    if fields.get("material_type"):
        m_name, _ = match_master_entity("material", fields["material_type"])
        if m_name:
            fields["material_type"] = m_name

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
            actor,
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
                    image_path, raw_ocr_text, created_by, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    image_path, raw_ocr_text, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def resolve_system_ids(data: Dict[str, str]) -> Dict[str, str]:
    lookups = load_master_data()
    cust_val = data.get("sold_to", "")
    quarry_val = data.get("quarry_name", "")
    mat_val = data.get("material_type", "")

    _, cust_id = match_master_entity("customer", cust_val)
    _, quarry_id = match_master_entity("quarry", quarry_val)
    _, mat_id = match_master_entity("material", mat_val)

    return {
        "customer_id": cust_id or lookup_system_id("customer", cust_val, lookups),
        "quarry_id": quarry_id or lookup_system_id("quarry", quarry_val, lookups),
        "material_id": mat_id or lookup_system_id("material", mat_val, lookups),
    }


def validate_system_ids(data: Dict[str, str]) -> List[str]:
    if not MASTER_DATA_PATH.exists():
        return []

    ids = resolve_system_ids(data)
    labels = {
        "customer_id": "Customer",
        "quarry_id": "Quarry",
        "material_id": "Material",
    }
    return [
        f"{labels[field]} is not in the master-data list. Correct the value or add an alias before approving."
        for field, system_id in ids.items()
        if not system_id
    ]


def approve_ticket(ticket_row_id: int, edited: Dict[str, str], reviewer: str = "unsecured") -> Optional[str]:
    if ticket_exists(edited["ticket_id"], edited["ticket_date"], ticket_row_id):
        logger.warning(
            "ticket_approve_blocked_duplicate row_id=%s ticket_id=%s date=%s",
            ticket_row_id,
            edited.get("ticket_id", ""),
            edited.get("ticket_date", ""),
        )
        return "Duplicate: an approved ticket with this number and date already exists."

    now = dt.datetime.utcnow().isoformat()
    system_ids = resolve_system_ids(edited)

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
            system_ids["customer_id"],
            system_ids["quarry_id"],
            system_ids["material_id"],
            reviewer,
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
                    customer_id = %s,
                    quarry_id = %s,
                    material_id = %s,
                    review_status = 'approved',
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
                    customer_id = ?,
                    quarry_id = ?,
                    material_id = ?,
                    review_status = 'approved',
                    reviewed_by = ?,
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


def export_approved_to_csv(exporter: str = "unsecured") -> Optional[Path]:
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
        now = dt.datetime.utcnow().isoformat()

        csv_headers = [
            "Customer",
            "Customer ID",
            "Ticket Date",
            "Quarry",
            "Quarry ID",
            "Product Name",
            "Material ID",
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
            "Exported At",
        ]
        db_fields = [
            "sold_to",
            "customer_id",
            "ticket_date",
            "quarry_name",
            "quarry_id",
            "material_type",
            "material_id",
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
                values = [row[field] for field in db_fields]
                values[2] = format_export_date(str(row["ticket_date"] or ""))
                values.append(now)
                writer.writerow(values)

        if bucket_enabled():
            upload_to_bucket(out_path, "exports")

        ids = [row["id"] for row in rows]
        if postgres_enabled():
            batch_cursor = conn.cursor()
            batch_cursor.execute(
                """
                INSERT INTO export_batches (file_name, exported_at, ticket_count, exported_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (file_name, now, len(rows), exporter),
            )
            batch_id = batch_cursor.fetchone()[0]
            conn.execute(
                f"UPDATE tickets SET exported_at = %s, export_batch_id = %s, updated_at = %s WHERE id IN ({_db_param_placeholder_count(len(ids))})",
                [now, batch_id, now, *ids],
            )
        else:
            batch_cursor = conn.execute(
                """
                INSERT INTO export_batches (file_name, exported_at, ticket_count, exported_by)
                VALUES (?, ?, ?, ?)
                """,
                (file_name, now, len(rows), exporter),
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
    st.subheader("Upload tickets")
    actor = current_actor()
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
        total_files = len(uploaded)
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        for file_idx, file in enumerate(uploaded):
            status_text.text(f"Processing file {file_idx+1} of {total_files}: '{file.name}'...")
            progress_bar.progress(file_idx / total_files)

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
                        total_pages = len(reader.pages)
                        pdf_pages_ingested = 0
                        for page_idx, page in enumerate(reader.pages):
                            status_text.text(f"Processing page {page_idx+1} of {total_pages} from '{file.name}'...")
                            if page.images:
                                for img_idx, img in enumerate(page.images):
                                    page_img_name = f"{timestamp}_p{page_idx+1}_{img_idx+1}_{file.name.rsplit('.', 1)[0]}.jpg"
                                    page_img_path = UPLOAD_DIR / page_img_name
                                    page_img_path.write_bytes(img.data)

                                    fields, confidence, provider_used = extract_ticket_data(page_img_path)
                                    raw_ocr_text = fields.pop("__raw_text", "")
                                    fields.pop("__ocr_warning", None)
                                    stored_page_reference = persist_file(page_img_path, "uploads")
                                    insert_ticket(fields, confidence, stored_page_reference, provider_used, raw_ocr_text, actor)
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
                insert_ticket(fields, confidence, stored_file_reference, provider_used, raw_ocr_text, actor)
                processed_count += 1
            except Exception as exc:
                logger.exception("upload_processing_failed file=%s error=%s", file.name, exc)
        status_text.empty()
        progress_bar.empty()
        st.success(f"Successfully processed and queued {processed_count} ticket item(s).")


def render_review_tab() -> None:
    st.subheader("2) Review Queue")

    pending = fetch_tickets(["needs_review", "auto_ready"])
    if not pending:
        st.info("No tickets in review queue.")
        return

    # ── Reviewer + ticket selector ─────────────────────────────────────────────
    reviewer = current_actor()
    if reviewer == "unsecured":
        reviewer = st.text_input("Reviewer name", value="office", key="reviewer_name")
    else:
        st.caption(f"Signed in as: {reviewer}")

    # ── Bulk approve auto-ready tickets button ──────────────────────────────
    auto_ready_candidates = []
    for r in pending:
        if r["review_status"] == "auto_ready":
            r_dict = dict(r)
            if not validate_system_ids(r_dict):
                g_c = _clean_num_str(r_dict.get("gross_weight", ""))
                t_c = _clean_num_str(r_dict.get("tare_weight", ""))
                n_c = _clean_num_str(r_dict.get("net_weight", ""))
                if g_c and t_c and n_c:
                    if abs((int(g_c) - int(t_c)) - int(n_c)) <= 10:
                        auto_ready_candidates.append(r)
                elif n_c:
                    auto_ready_candidates.append(r)

    if auto_ready_candidates:
        if st.button(f"⚡ Bulk Approve {len(auto_ready_candidates)} Auto-Ready Ticket(s)", key="bulk_approve_btn"):
            approved_cnt = 0
            for r in auto_ready_candidates:
                err = approve_ticket(r["id"], dict(r), reviewer)
                if not err:
                    approved_cnt += 1
            st.success(f"Successfully approved {approved_cnt} ticket(s)!")
            st.rerun()

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
        master_names = get_master_data_canonical_names()
        master_quarries = master_names.get("quarry", [])
        master_customers = master_names.get("customer", [])
        master_materials = master_names.get("material", [])

        with st.form(f"review_form_{selected_id}"):
            st.markdown("**Identity**")
            c1, c2 = st.columns(2)
            with c1:
                edited["ticket_id"]   = st.text_input("Ticket No.", value=row["ticket_id"] or "")
                
                raw_date_str = str(row["ticket_date"] or "").strip()
                default_date = dt.date.today()
                if raw_date_str:
                    try:
                        default_date = dt.date.fromisoformat(raw_date_str)
                    except ValueError:
                        for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y.%m.%d", "%d-%m-%Y", "%m-%d-%Y"):
                            try:
                                default_date = dt.datetime.strptime(raw_date_str, fmt).date()
                                break
                            except ValueError:
                                pass
                selected_date = st.date_input(
                    "Ticket Date (MM/DD/YYYY)",
                    value=default_date,
                    format="MM/DD/YYYY",
                    key=f"date_picker_{selected_id}",
                )
                edited["ticket_date"] = selected_date.isoformat() if selected_date else ""
                edited["job_no"]      = st.text_input("Job No.", value=row["job_no"] or "")
            with c2:
                captured_q = str(row["quarry_name"] or "").strip()
                quarry_options = list(master_quarries)
                if captured_q and captured_q not in quarry_options:
                    quarry_options.insert(0, captured_q)
                quarry_options.append("✏️ Custom Quarry...")

                q_idx = quarry_options.index(captured_q) if captured_q in quarry_options else 0
                sel_q = st.selectbox("Quarry", quarry_options, index=q_idx, key=f"q_sel_{selected_id}")
                if sel_q == "✏️ Custom Quarry...":
                    edited["quarry_name"] = st.text_input("Enter Custom Quarry Name", value=captured_q, key=f"q_custom_{selected_id}")
                else:
                    edited["quarry_name"] = sel_q

                captured_cust = str(row["sold_to"] or "").strip()
                cust_options = list(master_customers)
                if captured_cust and captured_cust not in cust_options:
                    cust_options.insert(0, captured_cust)
                cust_options.append("✏️ Custom Customer...")

                c_idx = cust_options.index(captured_cust) if captured_cust in cust_options else 0
                sel_cust = st.selectbox("Customer (Sold To)", cust_options, index=c_idx, key=f"cust_sel_{selected_id}")
                if sel_cust == "✏️ Custom Customer...":
                    edited["sold_to"] = st.text_input("Enter Custom Customer Name", value=captured_cust, key=f"cust_custom_{selected_id}")
                else:
                    edited["sold_to"] = sel_cust

                captured_mat = str(row["material_type"] or "").strip()
                common_mats = ["Crusher Run", "3/4 Clear", "Hot Mix", "Stone Dust", "Rip Rap", "Pit Run", "Fill", "Aggregate", "Asphalt"]
                mat_options = list(dict.fromkeys(([captured_mat] if captured_mat else []) + master_materials + common_mats))
                mat_options.append("✏️ Custom Material...")

                m_idx = mat_options.index(captured_mat) if captured_mat in mat_options else 0
                sel_mat = st.selectbox("Material", mat_options, index=m_idx, key=f"mat_sel_{selected_id}")
                if sel_mat == "✏️ Custom Material...":
                    edited["material_type"] = st.text_input("Enter Custom Material Name", value=captured_mat, key=f"mat_custom_{selected_id}")
                else:
                    edited["material_type"] = sel_mat

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

            override_mismatch = st.checkbox("Override weight mismatch (if ticket scale image math is wrong)", value=False)

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
        if save_clicked:
            errors = validate_required(edited)
            errors.extend(validate_system_ids(edited))
            deliver_to_issue = validate_deliver_to_quality(edited.get("deliver_to", ""))
            if deliver_to_issue:
                errors.append(deliver_to_issue)
            g_clean = _clean_num_str(edited.get("gross_weight", ""))
            t_clean = _clean_num_str(edited.get("tare_weight",  ""))
            n_clean = _clean_num_str(edited.get("net_weight",   ""))
            if g_clean and t_clean and n_clean:
                expected = int(g_clean) - int(t_clean)
                if abs(expected - int(n_clean)) > 10 and not override_mismatch:
                    errors.append(
                        f"Net mismatch: Gross ({int(g_clean):,}) − Tare ({int(t_clean):,}) = {expected:,}, but entered Net is {edited.get('net_weight')}. "
                        "Check 'Override weight mismatch' above if the physical ticket math is incorrect."
                    )
            if errors:
                for err in errors:
                    st.error(err)
            else:
                err_msg = approve_ticket(selected_id, edited, reviewer)
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
        out_path = export_approved_to_csv(current_actor())
        if not out_path:
            st.info("No unexported approved tickets available.")
        else:
            st.session_state["latest_export_download"] = {
                "file_name": out_path.name,
                "data": out_path.read_bytes(),
            }
            st.success("Export created. Download the CSV below.")

    export_download = st.session_state.get("latest_export_download")
    if export_download:
        st.download_button(
            "Download exported CSV",
            data=export_download["data"],
            file_name=export_download["file_name"],
            mime="text/csv",
            type="primary",
        )


def render_history_tab() -> None:
    st.subheader("5) Ticket History")
    completed = fetch_tickets(["approved", "rejected"])
    if not completed:
        st.info("No processed tickets yet.")
        return

    history_view = st.radio(
        "View mode",
        ["Individual Ticket", "Browse by Customer"],
        horizontal=True,
        key="history_view_mode",
    )

    if history_view == "Browse by Customer":
        _render_browse_by_customer(completed)
    else:
        _render_individual_ticket_history(completed)

    st.divider()
    st.subheader("Export Batch Archive")
    _render_export_batch_archive()


def _render_browse_by_customer(completed: list) -> None:
    """Group approved tickets by customer and date for browsing and batch download."""
    import io
    import zipfile

    approved = [r for r in completed if r["review_status"] == "approved"]
    if not approved:
        st.info("No approved tickets to browse.")
        return

    # Build customer → date → tickets index
    by_customer: Dict[str, List[Any]] = {}
    for row in approved:
        customer = str(row["sold_to"] or "Unknown Customer").strip()
        by_customer.setdefault(customer, []).append(row)

    customer_names = sorted(by_customer.keys(), key=str.lower)
    selected_customer = st.selectbox(
        "Customer",
        customer_names,
        key="browse_customer_select",
    )
    if not selected_customer:
        return

    customer_tickets = by_customer[selected_customer]
    # Sort by date descending
    customer_tickets.sort(key=lambda r: str(r["ticket_date"] or ""), reverse=True)

    # Date filter
    available_dates = sorted(
        {str(r["ticket_date"] or "No date") for r in customer_tickets}, reverse=True
    )
    selected_dates = st.multiselect(
        "Filter by date (leave empty for all)",
        available_dates,
        key="browse_customer_date_filter",
    )
    if selected_dates:
        customer_tickets = [
            r for r in customer_tickets
            if str(r["ticket_date"] or "No date") in selected_dates
        ]

    st.caption(f"{len(customer_tickets)} ticket(s) for **{selected_customer}**")
    st.dataframe(
        [
            {
                "Ticket #": row["ticket_id"],
                "Date": row["ticket_date"],
                "Quarry": row["quarry_name"],
                "Material": row["material_type"],
                "Net": row["net_weight"],
                "Exported": row["exported_at"] or "No",
            }
            for row in customer_tickets
        ],
        use_container_width=True,
        hide_index=True,
    )

    # Batch download as ZIP
    if st.button(
        f"Download all {len(customer_tickets)} ticket image(s) as ZIP",
        key="browse_customer_batch_download",
    ):
        zip_buffer = io.BytesIO()
        included = 0
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for row in customer_tickets:
                image_bytes = load_stored_file(row["image_path"])
                if image_bytes:
                    date_part = str(row["ticket_date"] or "no_date").replace("/", "-")
                    ticket_num = str(row["ticket_id"] or row["id"])
                    ext = Path(str(row["image_path"])).suffix or ".png"
                    filename = f"{date_part}/{ticket_num}{ext}"
                    zf.writestr(filename, image_bytes)
                    included += 1
        if included:
            safe_name = re.sub(r"[^\w\- ]", "_", selected_customer)[:60]
            st.download_button(
                f"Save ZIP ({included} image(s))",
                data=zip_buffer.getvalue(),
                file_name=f"{safe_name}_tickets.zip",
                mime="application/zip",
                key="browse_customer_zip_download",
            )
        else:
            st.warning("No ticket images could be loaded for this customer.")


def _render_individual_ticket_history(completed: list) -> None:
    """Original individual ticket history view."""
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
            st.download_button(
                "Download ticket image",
                data=image_bytes,
                file_name=Path(str(row["image_path"])).name,
                key=f"download_ticket_{selected_id}",
            )
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


def _render_export_batch_archive() -> None:
    """Display export batch archive with batch reopening capability."""
    batches = fetch_export_batches()
    if not batches:
        st.info("No export batches have been created since batch archiving was enabled.")
        return

    batch_options = {
        f"Batch #{batch['id']} | {batch['file_name']} | {batch['ticket_count']} ticket(s) | {batch['exported_at']} | {batch['exported_by'] or 'unsecured'}": batch["id"]
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

    actor = require_authenticated_actor()
    ensure_paths()
    init_db()
    logger.info(
        "app_start provider_env=%s duplicate_check_enabled=%s",
        os.getenv("OCR_PROVIDER", "").strip().lower() or "<empty>",
        duplicates_check_enabled(),
    )
    if actor == "unsecured":
        st.warning("Access control is not configured. Set APP_ACCESS_PASSWORD before production use.")

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
    st.title("Nova Construction — Ticket Processing")
    st.divider()

    tabs = st.tabs(["Upload", "Review", "Exports", "History", "System"])

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
