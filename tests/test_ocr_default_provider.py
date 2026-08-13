from pathlib import Path

from PIL import Image

import ocr


def test_extract_ticket_data_defaults_to_easyocr(monkeypatch):
    monkeypatch.delenv("OCR_PROVIDER", raising=False)

    captured = {}

    def fake_google(path: Path):
        raise RuntimeError("google should not be used by default")

    def fake_easyocr(path: Path):
        captured["used"] = "easyocr"
        return {"ticket_id": "", "__raw_text": ""}, 0.0

    def fake_pytesseract(path: Path):
        raise RuntimeError("pytesseract should not be used when EasyOCR succeeds")

    monkeypatch.setattr(ocr, "_extract_with_google_vision", fake_google)
    monkeypatch.setattr(ocr, "_extract_with_easyocr", fake_easyocr)
    monkeypatch.setattr(ocr, "_extract_with_pytesseract", fake_pytesseract)

    result = ocr.extract_ticket_data(Path("dummy.png"))

    assert result[2] == "easyocr"
    assert captured["used"] == "easyocr"


def test_development_launcher_defaults_to_easyocr():
    launcher = Path(ocr.__file__).with_name("run.bat")
    contents = launcher.read_text(encoding="utf-8")

    assert 'set "OCR_PROVIDER=easyocr"' in contents
    assert 'set "OCR_PROVIDER=pytesseract"' not in contents


def test_configure_tesseract_uses_system_binary_on_linux(monkeypatch):
    captured = {}

    def fake_which(executable):
        captured["which"] = executable
        return "/usr/bin/tesseract"

    monkeypatch.setattr(ocr, "shutil", type("S", (), {"which": staticmethod(fake_which)}), raising=False)

    result = ocr._configure_tesseract_cmd()

    assert captured["which"] == "tesseract"
    assert result == "/usr/bin/tesseract"


def test_extract_quarry_name_uses_form_text_without_embedded_names():
    assert ocr._extract_quarry_name("SAMPLE MATERIAL QUARRY\n") == "Sample Material"


def test_sanitize_untrusted_fields_rejects_header_and_identifier_bleed():
    parsed = {
        "ticket_id": "12345",
        "job_no": "Sample Quarry",
        "received_by": "12345",
        "deliver_to": "42",
        "sold_to": "Valid Customer",
        "trucker": "A#",
        "material_type": "Road Base",
    }

    ocr._sanitize_untrusted_fields(parsed)

    assert parsed["job_no"] == ""
    assert parsed["received_by"] == ""
    assert parsed["deliver_to"] == ""
    assert parsed["trucker"] == ""
    assert parsed["sold_to"] == "Valid Customer"
    assert parsed["material_type"] == "Road Base"


def test_sanitize_untrusted_fields_rejects_ticket_number_and_label_fragments():
    parsed = {
        "ticket_id": "07235",
        "gross_weight": "",
        "tare_weight": "7235",
        "net_weight": "14450",
        "sold_to": "ee",
        "material_type": "GROS",
        "deliver_to": "ES",
        "trucker": "an ed",
    }

    ocr._sanitize_untrusted_fields(parsed)

    assert parsed["tare_weight"] == ""
    assert parsed["net_weight"] == "14450"
    assert parsed["sold_to"] == ""
    assert parsed["material_type"] == ""


def test_tesseract_orientation_selection_prefers_readable_form(monkeypatch):
    class FakeImage:
        def rotate(self, angle, expand):
            return angle

    monkeypatch.setattr(ocr, "_preprocess_for_ocr", lambda image: image)

    def read_text(_image, angle):
        if angle == 90:
            return "DATE May 13/26 GROSS 25000 TARE 9800 NET 15200 MATERIAL Type 1"
        return "unreadable"

    prepared, raw_text, parsed, score, angle = ocr._select_tesseract_candidate(FakeImage(), read_text)

    assert prepared == 90
    assert angle == 90
    assert raw_text.startswith("DATE")
    assert parsed["gross_weight"] == "25000"
    assert score > 0


def test_form_label_hits_identifies_upright_ticket_form():
    raw_text = "DATE JOB NO LICENSE PLATE TRUCKER SOLD TO DELIVER TO MATERIAL GROSS TARE NET RECEIVED BY"

    assert ocr._form_label_hits(raw_text) == 11


def test_persist_upright_image_rotates_stored_preview(tmp_path):
    image_path = tmp_path / "ticket.jpg"
    source = Image.new("RGB", (80, 40), "red")

    ocr._persist_upright_image(image_path, source, 90)
    source.close()

    with Image.open(image_path) as stored:
        assert stored.size == (40, 80)
