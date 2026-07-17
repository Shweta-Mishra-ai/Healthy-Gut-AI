import io
import re


def markdown_to_docx_bytes(title: str, markdown_text: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(title or "Article", level=1)

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        elif stripped.startswith("|"):
            # skip raw markdown table rows; tables need dedicated handling
            continue
        else:
            clean = re.sub(r"[*_`]", "", stripped)
            doc.add_paragraph(clean)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def markdown_to_pdf_bytes(title: str, markdown_text: str) -> bytes:
    from fpdf import FPDF

    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, (title or "Article").encode("latin-1", "replace").decode("latin-1"),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.set_font("Helvetica", size=11)

    for line in markdown_text.splitlines():
        stripped = line.strip()
        if not stripped:
            pdf.ln(3)
            continue
        clean = re.sub(r"[#*_`|]", "", stripped).strip()
        if not clean:
            continue
        safe = clean.encode("latin-1", "replace").decode("latin-1")
        pdf.multi_cell(0, 7, safe, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    out = pdf.output()
    return bytes(out)
