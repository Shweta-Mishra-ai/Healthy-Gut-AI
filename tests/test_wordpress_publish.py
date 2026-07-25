from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

from app.cms_wordpress import _markdown_to_basic_html, is_configured, publish_post
from app.cms_wordpress import test_connection as wp_test_connection
from app.main import app

client = TestClient(app)


def _approve_article(topic="WP Publish Test Topic", keyword="IBS diet"):
    gen = client.post("/generate", json={"topic": topic, "primary_keyword": keyword, "geo_target": "USA"}).json()
    review_id = gen["review_id"]
    client.post(f"/review/{review_id}/approve", json={"note": ""})
    return review_id


# --- Configuration state ---

def test_not_configured_by_default():
    assert is_configured() is False


def test_status_endpoint_reflects_unconfigured_state():
    r = client.get("/publish/wordpress/status")
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_publish_without_config_returns_clear_error():
    result = publish_post(title="T", article_markdown="# Hello", dry_run=False)
    assert result["success"] is False
    assert "not configured" in result["error"].lower()


def test_test_connection_without_config_returns_clear_error():
    result = wp_test_connection()
    assert result["connected"] is False
    assert "not configured" in result["error"].lower()


# --- Dry run (works without any config, by design) ---

def test_dry_run_never_hits_network():
    with patch("app.cms_wordpress.requests.post") as mock_post:
        result = publish_post(title="Dry Run Title", article_markdown="# Hello world", dry_run=True)
        mock_post.assert_not_called()
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["would_send"]["title"] == "Dry Run Title"
    assert result["would_send"]["status"] == "draft"


# --- Mocked successful publish (simulating a real WordPress site) ---

@patch("app.cms_wordpress.settings")
@patch("app.cms_wordpress.requests.post")
def test_publish_success_mocked(mock_post, mock_settings):
    mock_settings.WORDPRESS_URL = "https://example.com"
    mock_settings.WORDPRESS_USERNAME = "admin"
    mock_settings.WORDPRESS_APP_PASSWORD = "fake app pass"
    mock_settings.WORDPRESS_TIMEOUT_SECONDS = 15

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": 42, "link": "https://example.com/?p=42", "status": "draft"}
    mock_post.return_value = mock_resp

    result = publish_post(title="Real Publish", article_markdown="# Heading\n\nSome text.", dry_run=False)
    assert result["success"] is True
    assert result["post_id"] == 42
    assert result["post_url"] == "https://example.com/?p=42"


@patch("app.cms_wordpress.settings")
@patch("app.cms_wordpress.requests.post")
def test_publish_auth_failure_mocked(mock_post, mock_settings):
    mock_settings.WORDPRESS_URL = "https://example.com"
    mock_settings.WORDPRESS_USERNAME = "admin"
    mock_settings.WORDPRESS_APP_PASSWORD = "wrong"
    mock_settings.WORDPRESS_TIMEOUT_SECONDS = 15

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_post.return_value = mock_resp

    result = publish_post(title="T", article_markdown="# H", dry_run=False)
    assert result["success"] is False
    assert "authentication" in result["error"].lower()


@patch("app.cms_wordpress.settings")
@patch("app.cms_wordpress.requests.post")
def test_publish_connection_error_mocked(mock_post, mock_settings):
    mock_settings.WORDPRESS_URL = "https://nonexistent-site-xyz.example"
    mock_settings.WORDPRESS_USERNAME = "admin"
    mock_settings.WORDPRESS_APP_PASSWORD = "pass"
    mock_settings.WORDPRESS_TIMEOUT_SECONDS = 15
    mock_post.side_effect = requests.exceptions.ConnectionError("Name resolution failed")

    result = publish_post(title="T", article_markdown="# H", dry_run=False)
    assert result["success"] is False
    assert "connect" in result["error"].lower()


@patch("app.cms_wordpress.settings")
@patch("app.cms_wordpress.requests.post")
def test_publish_timeout_mocked(mock_post, mock_settings):
    mock_settings.WORDPRESS_URL = "https://slow-site.example"
    mock_settings.WORDPRESS_USERNAME = "admin"
    mock_settings.WORDPRESS_APP_PASSWORD = "pass"
    mock_settings.WORDPRESS_TIMEOUT_SECONDS = 15
    mock_post.side_effect = requests.exceptions.Timeout("Request timed out")

    result = publish_post(title="T", article_markdown="# H", dry_run=False)
    assert result["success"] is False
    assert "timed out" in result["error"].lower() or "timeout" in result["error"].lower()


@patch("app.cms_wordpress.settings")
@patch("app.cms_wordpress.requests.post")
def test_publish_rejected_by_wp_mocked(mock_post, mock_settings):
    mock_settings.WORDPRESS_URL = "https://example.com"
    mock_settings.WORDPRESS_USERNAME = "admin"
    mock_settings.WORDPRESS_APP_PASSWORD = "pass"
    mock_settings.WORDPRESS_TIMEOUT_SECONDS = 15

    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.json.return_value = {"code": "rest_invalid_param", "message": "Invalid slug."}
    mock_post.return_value = mock_resp

    result = publish_post(title="T", article_markdown="# H", slug="bad slug!!", dry_run=False)
    assert result["success"] is False
    assert "invalid slug" in result["error"].lower()


@patch("app.cms_wordpress.settings")
@patch("app.cms_wordpress.requests.get")
def test_connection_test_success_mocked(mock_get, mock_settings):
    mock_settings.WORDPRESS_URL = "https://example.com"
    mock_settings.WORDPRESS_USERNAME = "admin"
    mock_settings.WORDPRESS_APP_PASSWORD = "pass"
    mock_settings.WORDPRESS_TIMEOUT_SECONDS = 15

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"name": "Admin User"}
    mock_get.return_value = mock_resp

    result = wp_test_connection()
    assert result["connected"] is True
    assert result["user"] == "Admin User"


# --- Markdown -> HTML conversion ---

def test_markdown_to_html_basic_conversion():
    html = _markdown_to_basic_html("# Title\n\nSome **bold** and *italic* text.\n\n## Subheading")
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<h2>Subheading</h2>" in html


def test_markdown_to_html_skips_tables():
    html = _markdown_to_basic_html("# T\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert "|" not in html


# --- Business rules enforced at the API layer (app/main.py) ---

def test_cannot_publish_a_draft_article():
    gen = client.post("/generate", json={"topic": "Not yet approved topic", "primary_keyword": "IBS diet", "geo_target": "USA"}).json()
    r = client.post(f"/publish/wordpress/{gen['review_id']}")
    assert r.status_code == 409


def test_cannot_publish_a_rejected_article():
    gen = client.post("/generate", json={"topic": "Rejected topic test", "primary_keyword": "IBS diet", "geo_target": "USA"}).json()
    client.post(f"/review/{gen['review_id']}/reject", json={"note": ""})
    r = client.post(f"/publish/wordpress/{gen['review_id']}")
    assert r.status_code == 409


def test_publish_nonexistent_article_returns_404():
    r = client.post("/publish/wordpress/doesnotexist123")
    assert r.status_code == 404


def test_publish_invalid_status_param_rejected():
    review_id = _approve_article()
    r = client.post(f"/publish/wordpress/{review_id}?status=not_a_real_status")
    assert r.status_code == 422


def test_publish_dry_run_works_even_without_wordpress_configured():
    review_id = _approve_article()
    r = client.post(f"/publish/wordpress/{review_id}?dry_run=true")
    assert r.status_code == 200
    body = r.json()
    assert body["dry_run"] is True
    assert body["would_send"]["status"] == "draft"


def test_publish_without_dry_run_fails_cleanly_when_unconfigured():
    review_id = _approve_article()
    r = client.post(f"/publish/wordpress/{review_id}?dry_run=false")
    assert r.status_code == 502
    assert "not configured" in r.json()["error"].lower()
