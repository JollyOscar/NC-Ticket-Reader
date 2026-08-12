import random
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app


def print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main() -> None:
    random.seed(42)

    root = Path(__file__).resolve().parents[1]
    images_dir = root / "docs" / "client_research" / "Info provided" / "Images"

    # Start clean for a clear demo run.
    if app.DB_PATH.exists():
        app.DB_PATH.unlink()
    if app.UPLOAD_DIR.exists():
        shutil.rmtree(app.UPLOAD_DIR)
    if app.EXPORT_DIR.exists():
        for old_file in app.EXPORT_DIR.glob("*.csv"):
            try:
                old_file.unlink()
            except PermissionError:
                # File may be open in editor; keep going and create a new export file.
                pass

    app.ensure_paths()
    app.init_db()

    ticket_files = sorted(images_dir.glob("Ticket example *.jpg"))
    if not ticket_files:
        raise SystemExit(f"No ticket images found in {images_dir}")

    print_header("STEP 1 - INGEST TICKET IMAGES")
    for img in ticket_files:
        copied = app.UPLOAD_DIR / img.name
        shutil.copy2(img, copied)
        fields, confidence, provider = app.extract_ticket_data(copied)
        app.insert_ticket(fields, confidence, str(copied), provider)
        print(
            f"Ingested: {img.name} | provider={provider} | confidence={confidence} | "
            f"ticket_id={fields['ticket_id']}"
        )

    print_header("STEP 2 - REVIEW QUEUE")
    pending = app.fetch_tickets(["needs_review", "auto_ready"])
    for row in pending:
        print(
            f"Queue Row #{row['id']}: status={row['review_status']} conf={row['confidence_score']} "
            f"ticket_id={row['ticket_id']}"
        )

    print_header("STEP 3 - APPROVE RECORDS")
    reviewer = "alex.demo"
    for row in pending:
        edited = {
            "ticket_id": row["ticket_id"],
            "ticket_date": row["ticket_date"],
            "job_no": row["job_no"],
            "quarry_name": row["quarry_name"],
            "truck_or_plate": row["truck_or_plate"],
            "trucker": row["trucker"],
            "sold_to": row["sold_to"],
            "deliver_to": row["deliver_to"],
            "material_type": row["material_type"],
            "received_by": row["received_by"],
            "gross_weight": row["gross_weight"],
            "tare_weight": row["tare_weight"],
            "net_weight": row["net_weight"],
            "source_site": row["source_site"],
            "destination_site": row["destination_site"],
        }
        err = app.approve_ticket(row["id"], edited)
        if err:
            print(f"Could not approve row #{row['id']}: {err}")
        else:
            approved = app.fetch_ticket(row["id"])
            print(
                f"Approved row #{row['id']} -> invoice={approved['invoice_number']} "
                f"invoice_status={approved['invoice_status']}"
            )

    print_header("STEP 4 - EXPORT APPROVED TO CSV")
    export_path = app.export_approved_to_csv()
    if not export_path:
        print("No newly approved rows to export.")
    else:
        print(f"CSV Export: {export_path}")

    print_header("STEP 5 - FINAL STATUS SUMMARY")
    rows = app.fetch_tickets()
    status_counts = {}
    for row in rows:
        status_counts[row["review_status"]] = status_counts.get(row["review_status"], 0) + 1
    print(f"Total rows: {len(rows)}")
    print(f"By status: {status_counts}")


if __name__ == "__main__":
    main()
