import csv
import io
import re
import zipfile


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


def _safe_filename(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\-]+", "-", (text or fallback).strip().lower()).strip("-")
    return slug or fallback


def build_batch_zip(items: list[dict]) -> bytes:
    """Bundles a batch of generation results into one ZIP: one .docx per
    successful article, plus a batch_summary.csv covering every item
    (including failures, so the CSV is a complete audit trail of the run)."""
    buf = io.BytesIO()
    csv_buf = io.StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(["Topic", "Keyword", "Geo", "Status", "Provider", "Words", "Readability", "KeywordDensity%", "Error"])

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        used_names = set()
        for item in items:
            req = item["request"]
            result = item["result"]
            topic, keyword, geo = req.get("topic", ""), req.get("primary_keyword", ""), req.get("geo_target", "")

            if "error" in result:
                writer.writerow([topic, keyword, geo, "FAILED", "", "", "", "", result["error"]])
                continue

            article_md = result.get("optimized_article_markdown", "")
            word_count = len(article_md.split())
            readability = result.get("metrics", {}).get("readability", {}).get("fleschReadingEase", "")
            density = result.get("metrics", {}).get("keywordDensity", {}).get("keywordDensityPercent", "")
            writer.writerow([topic, keyword, geo, "OK", result.get("provider_used", ""), word_count, readability, density, ""])

            base_name = _safe_filename(topic, f"article-{len(used_names) + 1}")
            filename = f"{base_name}.docx"
            n = 2
            while filename in used_names:
                filename = f"{base_name}-{n}.docx"
                n += 1
            used_names.add(filename)

            docx_bytes = markdown_to_docx_bytes(topic, article_md)
            zf.writestr(filename, docx_bytes)

        zf.writestr("batch_summary.csv", csv_buf.getvalue())

    return buf.getvalue()
