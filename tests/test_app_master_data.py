import csv

import app


def test_resolve_system_ids_matches_names_and_aliases(monkeypatch, tmp_path):
    master_data = tmp_path / "master_data.csv"
    master_data.write_text(
        "entity_type,name,system_id,aliases\n"
        "customer,Acme Construction,CUST-001,Acme\n"
        "quarry,Long Point,QUARRY-019,\n"
        "material,Crusher Run,MAT-042,CR\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "MASTER_DATA_PATH", master_data)

    assert app.resolve_system_ids(
        {"sold_to": "acme", "quarry_name": "Long Point", "material_type": "CR"}
    ) == {
        "customer_id": "CUST-001",
        "quarry_id": "QUARRY-019",
        "material_id": "MAT-042",
    }


def test_match_master_entity_corrects_ocr_spelling_to_dropdown_option(monkeypatch, tmp_path):
    master_data = tmp_path / "master_data.csv"
    master_data.write_text(
        "entity_type,name,system_id,aliases\n"
        "customer,Acme Construction,CUST-001,Acme|Acme Const\n"
        "quarry,Long Point,QUARRY-019,Long Point Quarry\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "MASTER_DATA_PATH", master_data)

    assert app.match_master_entity("customer", "Acme Constrvction") == ("Acme Construction", "CUST-001")
    assert app.match_master_entity("quarry", "Long Piont") == ("Long Point", "QUARRY-019")


def test_format_export_date_uses_configured_netsuite_format(monkeypatch):
    monkeypatch.setenv("NETSUITE_DATE_FORMAT", "%m/%d/%Y")

    assert app.format_export_date("2026-08-13") == "08/13/2026"


def test_approval_persists_ids_and_exporter(monkeypatch, tmp_path):
    monkeypatch.setattr(app, "DB_PATH", tmp_path / "workflow.db")
    monkeypatch.setattr(app, "EXPORT_DIR", tmp_path)
    master_data = tmp_path / "master_data.csv"
    master_data.write_text(
        "entity_type,name,system_id,aliases\n"
        "customer,Acme Construction,CUST-001,\n"
        "quarry,Long Point,QUARRY-019,\n"
        "material,Crusher Run,MAT-042,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app, "MASTER_DATA_PATH", master_data)
    app.init_db()
    fields = {
        "ticket_id": "00123", "ticket_date": "2026-08-13", "truck_or_plate": "ABC123",
        "material_type": "Crusher Run", "job_no": "PO-1", "quarry_name": "Long Point",
        "trucker": "Taylor", "sold_to": "Acme Construction", "deliver_to": "12 Main Street",
        "received_by": "Receiver", "gross_weight": "25000", "tare_weight": "10000",
        "net_weight": "15000", "source_site": "", "destination_site": "",
    }
    app.insert_ticket(fields, 0.9, "ticket.jpg", "pytesseract", actor="Alex")
    ticket = app.fetch_tickets()[0]

    assert app.approve_ticket(ticket["id"], fields, reviewer="Jarrod") is None
    approved = app.fetch_ticket(ticket["id"])
    assert approved["created_by"] == "Alex"
    assert approved["reviewed_by"] == "Jarrod"
    assert approved["customer_id"] == "CUST-001"

    export_path = app.export_approved_to_csv("Jarrod")
    with export_path.open(newline="", encoding="utf-8") as exported:
        rows = list(csv.DictReader(exported))
    assert rows[0]["Customer ID"] == "CUST-001"
    assert rows[0]["Exported At"]
    assert app.fetch_export_batches()[0]["exported_by"] == "Jarrod"