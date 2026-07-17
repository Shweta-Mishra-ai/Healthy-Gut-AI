import importlib

from fastapi.testclient import TestClient


def _reload_app_with_api_key(monkeypatch, key: str):
    monkeypatch.setenv("API_KEY", key)
    from app import config, main
    importlib.reload(config)
    importlib.reload(main)
    return main


def test_generate_blocked_without_api_key_when_configured(monkeypatch):
    main = _reload_app_with_api_key(monkeypatch, "secret123")
    client = TestClient(main.app)
    payload = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "USA"}
    r = client.post("/generate", json=payload)
    assert r.status_code == 401
    monkeypatch.delenv("API_KEY", raising=False)


def test_generate_allowed_with_correct_api_key(monkeypatch):
    main = _reload_app_with_api_key(monkeypatch, "secret123")
    client = TestClient(main.app)
    payload = {"topic": "IBS diet plan unique2", "primary_keyword": "IBS diet", "geo_target": "USA"}
    r = client.post("/generate", json=payload, headers={"X-API-Key": "secret123"})
    assert r.status_code == 200
    monkeypatch.delenv("API_KEY", raising=False)


def test_health_not_protected_even_with_api_key_set(monkeypatch):
    main = _reload_app_with_api_key(monkeypatch, "secret123")
    client = TestClient(main.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["api_key_protected"] is True
    monkeypatch.delenv("API_KEY", raising=False)


def test_disclaimer_always_present_in_mock_output():
    from app.llm_providers import _mock_result
    result = _mock_result("random uncommon topic", "keyword", "USA")
    assert "disclaimer" in result["optimized_article_markdown"].lower()


def test_disclaimer_appended_if_missing():
    from app.llm_providers import _ensure_disclaimer
    text = "# Some Article\n\nNo disclaimer here at all."
    fixed = _ensure_disclaimer(text)
    assert "disclaimer" in fixed.lower()
    assert fixed.startswith("# Some Article")


def test_disclaimer_not_duplicated_if_present():
    from app.llm_providers import _ensure_disclaimer
    text = "# Article\n\n*Medical Disclaimer: consult a doctor.*"
    fixed = _ensure_disclaimer(text)
    assert fixed == text
