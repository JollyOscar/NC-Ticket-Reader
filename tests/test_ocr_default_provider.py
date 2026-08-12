from pathlib import Path

import ocr


def test_extract_ticket_data_defaults_to_pytesseract(monkeypatch):
    monkeypatch.delenv("OCR_PROVIDER", raising=False)

    captured = {}

    def fake_google(path: Path):
        raise RuntimeError("google should not be used by default")

    def fake_pytesseract(path: Path):
        captured["used"] = "pytesseract"
        return {"ticket_id": "", "__raw_text": ""}, 0.0

    monkeypatch.setattr(ocr, "_extract_with_google_vision", fake_google)
    monkeypatch.setattr(ocr, "_extract_with_pytesseract", fake_pytesseract)

    result = ocr.extract_ticket_data(Path("dummy.png"))

    assert result[2] == "pytesseract"
    assert captured["used"] == "pytesseract"


def test_configure_tesseract_uses_system_binary_on_linux(monkeypatch):
    captured = {}

    def fake_which(executable):
        captured["which"] = executable
        return "/usr/bin/tesseract"

    monkeypatch.setattr(ocr, "shutil", type("S", (), {"which": staticmethod(fake_which)}), raising=False)

    result = ocr._configure_tesseract_cmd()

    assert captured["which"] == "tesseract"
    assert result == "/usr/bin/tesseract"
