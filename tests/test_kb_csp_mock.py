import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mock_content import mock_result
from app.rag.knowledge_base import KNOWLEDGE_BASE, KnowledgeBaseError, load_knowledge_base, validate_entries
from app.rag.retriever import build_rag_context

client = TestClient(app)


def test_knowledge_base_loads_from_json_with_unique_ids():
    assert len(KNOWLEDGE_BASE) >= 25
    assert len({e["id"] for e in KNOWLEDGE_BASE}) == len(KNOWLEDGE_BASE)


@pytest.mark.parametrize("entries,message", [
    ([], "non-empty"),
    ([{"id": "a", "topic": "t", "title": "T"}], "'content'"),
    ([{"id": "a", "topic": "t", "title": "T", "content": "   "}], "'content'"),
    ([{"id": "a", "topic": "t", "title": "T", "content": "c"}, {"id": "a", "topic": "t", "title": "T", "content": "c"}], "duplicates"),
    (["not an object"], "not an object"),
])
def test_knowledge_base_validation_names_the_bad_entry(entries, message):
    with pytest.raises(KnowledgeBaseError, match=message):
        validate_entries(entries)


def test_knowledge_base_loader_reads_a_file(tmp_path):
    path = tmp_path / "kb.json"
    path.write_text(json.dumps([{"id": "x", "topic": "t", "title": "T", "content": "c"}]), encoding="utf-8")
    assert load_knowledge_base(str(path))[0]["id"] == "x"


@pytest.mark.parametrize("path", ["/", "/review", "/dashboard"])
def test_app_pages_send_a_strict_csp(path):
    csp = client.get(path).headers["content-security-policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-inline" not in csp
    assert "frame-ancestors 'none'" in csp


def test_csp_is_not_applied_to_api_docs_or_json():
    assert "content-security-policy" not in client.get("/docs").headers
    assert "content-security-policy" not in client.get("/health").headers


def test_app_pages_have_no_inline_scripts_or_styles():
    for path in ("/", "/review", "/dashboard"):
        html = client.get(path).text
        assert "<script>" not in html and "style=" not in html and "<style" not in html


def test_english_template_is_built_from_the_retrieved_chunks():
    result = mock_result("IBS diet plan", "IBS diet", "India")
    article = result["optimized_article_markdown"]
    _, chunks = build_rag_context("IBS diet plan", "IBS diet")
    for chunk in chunks:
        assert f"## {chunk['title']}" in article
    assert "Gut Symptom Red Flags" not in article.split("## When to See a Doctor")[0]
    assert "alarm features" in article
    assert len(article.split()) >= 700


def test_hindi_template_is_substantially_longer_than_before():
    article = mock_result("पेट में गैस", "गैस", "भारत", language="hi")["optimized_article_markdown"]
    assert len(article.split()) >= 450
    assert "डॉक्टर से कब मिलें" in article


def test_export_joins_soft_wrapped_lines_into_one_paragraph():
    """Each line used to become its own DOCX/PDF paragraph, so any wrapped
    paragraph (from a model or the template) came out in fragments."""
    from app.export import _parse_blocks
    blocks = list(_parse_blocks("# T\n\nFirst line of a paragraph\ncontinues here.\n\n- item one\n- item two\nNext para."))
    assert ("para", "First line of a paragraph continues here.") in blocks
    assert ("bullet", "item one") in blocks and ("bullet", "item two") in blocks
    assert ("para", "Next para.") in blocks


def test_template_drops_weakly_related_chunks_as_sections():
    article = mock_result("Acid reflux triggers", "acid reflux", "India")["optimized_article_markdown"]
    assert "## Acid Reflux / GERD" in article
    assert "## Gastritis" not in article  # scores ~14% of the GERD match
