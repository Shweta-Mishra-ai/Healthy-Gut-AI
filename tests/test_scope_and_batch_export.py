import zipfile
import io

from fastapi.testclient import TestClient

from app.main import app
from app.rag.retriever import is_in_domain

client = TestClient(app)


def test_gut_health_topic_is_in_domain():
    assert is_in_domain("IBS diet plan", "IBS symptoms") is True


def test_unrelated_topic_is_out_of_domain():
    assert is_in_domain("infectious disease epidemiology", "epidemiology trends") is False


def test_hindi_gut_health_topic_is_in_domain():
    """Regression test: the topic/keyword fields are free text, and a
    Hindi-language generation request often has the topic itself typed in
    Devanagari, not just the output language selected. The domain check
    used to only recognize English gut-health terms and then fall back to
    TF-IDF similarity against an all-English knowledge base — which scores
    ~0 for Hindi text — so a completely on-topic Hindi query like
    "constipation home remedies" was silently rejected as out-of-scope.
    From the UI this looked exactly like a random/unexplained error."""
    assert is_in_domain("कब्ज़ के घरेलू उपाय", "कब्ज़ का इलाज") is True
    assert is_in_domain("पेट में गैस और सूजन", "गैस की समस्या") is True


def test_hindi_unrelated_topic_is_out_of_domain():
    assert is_in_domain("क्वांटम कंप्यूटिंग", "क्वांटम") is False


def test_generate_accepts_hindi_typed_gut_health_topic():
    payload = {"topic": "कब्ज़ के घरेलू उपाय", "primary_keyword": "कब्ज़ का इलाज", "geo_target": "India", "language": "hi"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    assert "wordCount" in r.json()["metrics"]


def test_generate_rejects_out_of_scope_topic():
    payload = {"topic": "infectious disease epidemiology", "primary_keyword": "epidemiology", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 422
    assert r.json()["out_of_scope"] is True


def test_generate_accepts_in_scope_topic():
    payload = {"topic": "Crohns disease diet", "primary_keyword": "Crohns disease", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 200
    assert "wordCount" in r.json()["metrics"]


def test_batch_zip_export_contains_docx_and_csv():
    payload = {"items": [
        {"topic": "IBS diet plan zip test", "primary_keyword": "IBS diet", "geo_target": "USA"},
        {"topic": "GERD relief zip test", "primary_keyword": "acid reflux", "geo_target": "UK"},
    ]}
    r = client.post("/export/batch/zip", json=payload)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "batch_summary.csv" in names
    docx_files = [n for n in names if n.endswith(".docx")]
    assert len(docx_files) == 2

    csv_content = zf.read("batch_summary.csv").decode("utf-8")
    assert "Topic" in csv_content
    assert "OK" in csv_content


def test_batch_zip_includes_failed_rows_in_csv():
    payload = {"items": [
        {"topic": "infectious disease epidemiology", "primary_keyword": "epidemiology", "geo_target": "USA"},
    ]}
    r = client.post("/export/batch/zip", json=payload)
    assert r.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    csv_content = zf.read("batch_summary.csv").decode("utf-8")
    assert "FAILED" in csv_content
