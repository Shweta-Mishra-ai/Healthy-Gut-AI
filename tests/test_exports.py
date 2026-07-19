from app.export import markdown_to_docx_bytes, markdown_to_pdf_bytes


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
