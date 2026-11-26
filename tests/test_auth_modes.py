"""The deployment fails closed: without API_KEY, every route that generates,
reviews, publishes or reveals the article library is disabled unless
ALLOW_UNAUTHENTICATED is set explicitly (local development)."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import app.main as main_module

client = TestClient(main_module.app)

PAYLOAD = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "India"}


@pytest.fixture
def no_key_closed(monkeypatch):
    monkeypatch.setattr(main_module.settings, "API_KEY", "")
    monkeypatch.setattr(main_module.settings, "ALLOW_UNAUTHENTICATED", False)


@pytest.fixture
def no_key_open(monkeypatch):
    monkeypatch.setattr(main_module.settings, "API_KEY", "")
    monkeypatch.setattr(main_module.settings, "ALLOW_UNAUTHENTICATED", True)


@pytest.mark.parametrize("method,path", [
    ("POST", "/generate"), ("POST", "/review/x/approve"), ("POST", "/publish/wordpress/x"),
    ("GET", "/review/queue"), ("GET", "/dashboard/stats"), ("GET", "/articles/x/export/pdf"),
    ("POST", "/analyze"), ("GET", "/internal-links?topic=IBS"),
])
def test_without_api_key_protected_routes_are_disabled_by_default(no_key_closed, method, path):
    r = client.request(method, path, json=PAYLOAD)
    assert r.status_code == 503
    assert "API_KEY" in r.json()["error"]


@pytest.mark.parametrize("path", ["/", "/review", "/dashboard", "/health", "/outline?topic=IBS"])
def test_pages_and_health_stay_reachable_without_a_key(no_key_closed, path):
    assert client.get(path).status_code == 200


def test_health_reports_auth_mode_and_no_filesystem_path(no_key_closed):
    body = client.get("/health").json()
    assert body["auth"] == "disabled"
    assert "path" not in body["database"]


def test_open_mode_never_allows_a_live_wordpress_publish(no_key_open):
    article = client.post("/generate", json=PAYLOAD).json()
    client.post(f"/review/{article['review_id']}/approve", json={})
    with patch("app.cms_wordpress.requests.post") as post:
        live = client.post(f"/publish/wordpress/{article['review_id']}?status=publish")
        dry = client.post(f"/publish/wordpress/{article['review_id']}?dry_run=true")
    assert live.status_code == 403 and "API_KEY" in live.json()["error"]
    assert dry.status_code == 200
    post.assert_not_called()


def test_library_routes_need_the_key_when_one_is_set(monkeypatch):
    monkeypatch.setattr(main_module.settings, "API_KEY", "k")
    assert client.get("/internal-links?topic=IBS").status_code == 401
    assert client.post("/analyze", json={"article_markdown": "IBS " * 30}).status_code == 401
    assert client.get("/internal-links?topic=IBS", headers={"X-API-Key": "k"}).status_code == 200


def test_generation_failure_does_not_leak_exception_text():
    with patch("app.routers.generation._generate_one", side_effect=RuntimeError("db password=hunter2")):
        r = client.post("/generate", json=PAYLOAD)
    assert r.status_code == 500
    assert "hunter2" not in r.text
