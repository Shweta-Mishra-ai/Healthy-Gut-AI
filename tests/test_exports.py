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
Some description.

## Section
- Bullet point 1
"""
    pdf_bytes = markdown_to_pdf_bytes("My Document", markdown_text)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0


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

