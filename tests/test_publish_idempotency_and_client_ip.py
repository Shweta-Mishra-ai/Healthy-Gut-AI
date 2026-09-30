import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def _approved_article_id(topic="IBS diet plan"):
    gen = client.post("/generate", json={"topic": topic, "primary_keyword": "IBS diet", "geo_target": "India"}).json()
    assert client.post(f"/review/{gen['review_id']}/approve", json={}).status_code == 200
    return gen["review_id"]


def _wp_response(status_code, post_id=101):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"id": post_id, "link": f"https://blog.example.com/?p={post_id}", "status": "draft"}
    return resp


@pytest.fixture
def wordpress_configured():
    with patch("app.cms_wordpress.settings") as s:
        s.WORDPRESS_URL = "https://blog.example.com"
        s.WORDPRESS_USERNAME = "editor"
        s.WORDPRESS_APP_PASSWORD = "app-pass"
        s.WORDPRESS_TIMEOUT_SECONDS = 5
        yield


def test_second_publish_updates_the_same_post_instead_of_duplicating(wordpress_configured):
    article_id = _approved_article_id()
    with patch("app.cms_wordpress.requests.post", return_value=_wp_response(201)) as post:
        first = client.post(f"/publish/wordpress/{article_id}")
        second = client.post(f"/publish/wordpress/{article_id}")

    assert first.status_code == 200 and second.status_code == 200
    assert post.call_args_list[0].args[0] == "https://blog.example.com/wp-json/wp/v2/posts"
    assert post.call_args_list[1].args[0] == "https://blog.example.com/wp-json/wp/v2/posts/101"
    assert second.json()["updated_existing"] is True

    item = client.get(f"/review/{article_id}").json()
    assert item["wp_post_id"] == 101
    assert item["wp_post_url"] == "https://blog.example.com/?p=101"


def test_post_deleted_in_wordpress_is_recreated(wordpress_configured):
    article_id = _approved_article_id()
    with patch("app.cms_wordpress.requests.post", return_value=_wp_response(201, post_id=101)):
        client.post(f"/publish/wordpress/{article_id}")
    with patch("app.cms_wordpress.requests.post",
               side_effect=[_wp_response(404), _wp_response(201, post_id=202)]) as post:
        r = client.post(f"/publish/wordpress/{article_id}")

    assert r.status_code == 200
    assert post.call_args_list[1].args[0] == "https://blog.example.com/wp-json/wp/v2/posts"
    assert client.get(f"/review/{article_id}").json()["wp_post_id"] == 202


def test_concurrent_publishes_create_only_one_post(wordpress_configured):
    article_id = _approved_article_id()
    created = []
    gate = threading.Barrier(2, timeout=5)

    def fake_post(url, **kwargs):
        if url.endswith("/posts"):
            created.append(url)
        return _wp_response(201)

    def publish():
        gate.wait()
        client.post(f"/publish/wordpress/{article_id}")

    with patch("app.cms_wordpress.requests.post", side_effect=fake_post):
        threads = [threading.Thread(target=publish) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(created) == 1


def test_dry_run_does_not_record_a_post(wordpress_configured):
    article_id = _approved_article_id()
    r = client.post(f"/publish/wordpress/{article_id}?dry_run=true")
    assert r.status_code == 200
    assert r.json()["updates_existing"] is False
    assert client.get(f"/review/{article_id}").json()["wp_post_id"] is None


@pytest.mark.parametrize("mode,expected", [("first", "1.2.3.4"), ("last", "10.0.0.9"), ("peer", "testclient")])
def test_client_ip_mode_selects_the_rate_limit_key(mode, expected):
    with patch.object(settings, "CLIENT_IP_MODE", mode):
        r = client.get("/debug/client-ip", headers={"X-Forwarded-For": "1.2.3.4, 10.0.0.9"})
    assert r.json()["rate_limit_key"] == expected


def test_last_mode_ignores_a_spoofed_leftmost_entry_for_rate_limiting():
    from app.rate_limit import rate_limiter
    rate_limiter._limit = 2
    payload = {"topic": "IBS diet plan", "primary_keyword": "IBS diet", "geo_target": "India"}
    with patch.object(settings, "CLIENT_IP_MODE", "last"):
        codes = [
            client.post("/generate", json=payload,
                        headers={"X-Forwarded-For": f"9.9.9.{i}, 10.0.0.9"}).status_code
            for i in range(3)
        ]
    assert codes[-1] == 429


def test_pages_declare_a_favicon():
    for path in ("/", "/review", "/dashboard"):
        assert 'rel="icon"' in client.get(path).text
