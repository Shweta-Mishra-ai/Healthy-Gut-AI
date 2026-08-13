from fastapi.testclient import TestClient
from app.export import markdown_to_docx_bytes, markdown_to_pdf_bytes
from app.main import app

client = TestClient(app)


def test_markdown_to_docx_conversion():
    markdown_text = """# Topic Header
Some description text.

## Section
- Bullet point 1
- Bullet point 2

| Table | Headers |
|---|---|
| Val 1 | Val 2 |
"""
    docx_bytes = markdown_to_docx_bytes("My Document", markdown_text)
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 0


def test_markdown_to_pdf_conversion():
    markdown_text = """# Topic Header
Some description with smart quotes “test” and dash — bullet •.

## Section
- Bullet point 1
"""
    pdf_bytes = markdown_to_pdf_bytes("My Document — Title", markdown_text)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


def test_markdown_to_pdf_preserves_hindi_text():
    # Regression test: Helvetica (FPDF's core font) only supports latin-1,
    # so encoding Devanagari with errors="ignore" used to silently delete
    # every Hindi character — a Hindi article exported to PDF came out as
    # blank lines with no error raised anywhere. Now a Unicode font is
    # embedded whenever the content contains Devanagari, and round-tripping
    # through a real PDF text extractor must recover the original text.
    import pdfplumber
    import io

    title = "आईबीएस डाइट टिप्स"
    body = "## परिचय\nयह एक टेस्ट लेख है जो पाचन स्वास्थ्य के बारे में है।"
    pdf_bytes = markdown_to_pdf_bytes(title, body)

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        extracted = pdf.pages[0].extract_text() or ""

    assert "आईबीएस" in extracted
    assert "पाचन स्वास्थ्य" in extracted


def test_export_endpoints_reject_out_of_scope_with_422():
    out_of_scope_payload = {
        "topic": "Quantum Computing Mechanics",
        "primary_keyword": "Quantum Computing",
        "geo_target": "USA",
    }
    for endpoint in ("/export/markdown", "/export/json", "/export/docx", "/export/pdf"):
        r = client.post(endpoint, json=out_of_scope_payload)
        assert r.status_code == 422
        body = r.json()
        assert body.get("out_of_scope") is True
        assert "error" in body



# --- Table preservation ------------------------------------------------
# Both exporters used to discard markdown tables: the DOCX writer skipped
# every line starting with '|', and the PDF writer stripped the pipes so the
# rows ran together as prose. The foods-to-eat/avoid table is often the most
# useful part of one of these articles.

TABLE_ARTICLE = """# IBS diet

Intro paragraph with **bold** text and a [link](https://example.test).

## Diet

| Foods to Eat | Foods to Avoid |
|---|---|
| Fermented yogurt | Fried foods |
| High-fiber vegetables | Processed snacks |

- first bullet
- second bullet
"""


def test_docx_export_keeps_tables_as_real_tables():
    import io
    import zipfile

    from app.export import markdown_to_docx_bytes

    data = markdown_to_docx_bytes("IBS diet", TABLE_ARTICLE)
    xml = zipfile.ZipFile(io.BytesIO(data)).read("word/document.xml").decode("utf-8")
    assert "<w:tbl>" in xml
    for cell in ("Foods to Eat", "Foods to Avoid", "Fermented yogurt", "Processed snacks"):
        assert cell in xml


def test_docx_export_strips_inline_markdown_but_keeps_link_text():
    import io
    import zipfile

    from app.export import markdown_to_docx_bytes

    xml = zipfile.ZipFile(io.BytesIO(markdown_to_docx_bytes("T", TABLE_ARTICLE))).read("word/document.xml").decode()
    assert "**bold**" not in xml
    assert "https://example.test" not in xml
    assert "link" in xml


def test_pdf_export_keeps_table_cell_text():
    import io

    import pdfplumber

    from app.export import markdown_to_pdf_bytes

    with pdfplumber.open(io.BytesIO(markdown_to_pdf_bytes("IBS diet", TABLE_ARTICLE))) as pdf:
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Foods to Eat" in text
    assert "Fermented yogurt" in text
    assert "|" not in text


def test_pdf_raises_instead_of_emitting_a_blank_hindi_document(monkeypatch):
    """Without the embedded font, Helvetica encodes Devanagari to latin-1 and
    drops every character — a 200 OK containing blank pages."""
    import pytest

    from app import export

    monkeypatch.setattr(export, "DEVANAGARI_FONT_PATH", "/nonexistent/font.ttf")
    with pytest.raises(export.FontUnavailableError):
        export.markdown_to_pdf_bytes("पाचन गाइड", "# पाचन गाइड\n\nपेट की सेहत के बारे में जानकारी।")


def test_pdf_export_endpoint_reports_a_missing_font_instead_of_succeeding(monkeypatch):
    from fastapi.testclient import TestClient

    from app import export
    from app.main import app

    monkeypatch.setattr(export, "DEVANAGARI_FONT_PATH", "/nonexistent/font.ttf")
    res = TestClient(app).post("/export/pdf", json={
        "topic": "पाचन स्वास्थ्य", "primary_keyword": "पाचन", "geo_target": "Delhi, India", "language": "hi",
    })
    assert res.status_code == 503
    assert "font" in res.json()["error"].lower()
