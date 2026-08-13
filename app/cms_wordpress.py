"""WordPress publishing via the WP REST API + Application Passwords.

Optional integration — same pattern as the LLM providers: if credentials
aren't configured, the feature is simply unavailable, and nothing else in
the app is affected. Requires:
  - WORDPRESS_URL      (e.g. https://yoursite.com)
  - WORDPRESS_USERNAME  (an existing WP user with author/editor/admin role)
  - WORDPRESS_APP_PASSWORD (generated under Users > Profile > Application
    Passwords in WP admin — NOT the account login password)

Publishes are created as WordPress drafts by default, never auto-published
live, so a bad request can't accidentally put unreviewed content on a real
site. Only articles with review_status == 'approved' are ever eligible
(enforced by the caller in app/main.py, not this module, so the rule is
visible at the API layer).
"""

import logging
import re

import requests

from app.config import settings

logger = logging.getLogger("gutfolio.wordpress")


def is_configured() -> bool:
    return bool(settings.WORDPRESS_URL and settings.WORDPRESS_USERNAME and settings.WORDPRESS_APP_PASSWORD)


def _auth():
    return (settings.WORDPRESS_USERNAME, settings.WORDPRESS_APP_PASSWORD)


def _friendly_error(exc: Exception) -> str:
    if isinstance(exc, requests.exceptions.ConnectTimeout):
        return f"Timed out connecting to {settings.WORDPRESS_URL} — check the URL and that the site is reachable."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return f"Could not connect to {settings.WORDPRESS_URL} — check WORDPRESS_URL is correct and the site is online."
    if isinstance(exc, requests.exceptions.Timeout):
        return "WordPress request timed out — the site may be slow or unreachable."
    return f"Unexpected error contacting WordPress: {exc}"


def test_connection() -> dict:
    """Verifies the configured credentials actually work, without publishing
    anything. Safe to call repeatedly — read-only."""
    if not is_configured():
        return {"connected": False, "error": "WordPress is not configured — set WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD."}

    url = f"{settings.WORDPRESS_URL}/wp-json/wp/v2/users/me"
    try:
        resp = requests.get(url, auth=_auth(), timeout=settings.WORDPRESS_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        logger.warning("WordPress connection test failed: %s", e)
        return {"connected": False, "error": _friendly_error(e)}

    if resp.status_code == 200:
        try:
            data = resp.json()
        except ValueError:
            return {"connected": False, "error": "Connected, but WordPress returned an unexpected (non-JSON) response."}
        return {"connected": True, "user": data.get("name", settings.WORDPRESS_USERNAME), "error": None}

    if resp.status_code in (401, 403):
        return {"connected": False, "error": "Authentication failed — check WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD."}
    if resp.status_code == 404:
        return {"connected": False, "error": f"WordPress REST API not found at {url} — check WORDPRESS_URL and that the REST API is enabled."}
    return {"connected": False, "error": f"WordPress returned HTTP {resp.status_code}."}


def _markdown_to_basic_html(markdown_text: str) -> str:
    """Minimal, dependency-free markdown->HTML for WordPress post content.
    Not a full renderer — handles headings, paragraphs, and bold/italic,
    which covers what this app's generated articles actually use."""
    lines = markdown_text.splitlines()
    html_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{stripped[4:]}</h3>")
        elif stripped.startswith("## "):
            html_lines.append(f"<h2>{stripped[3:]}</h2>")
        elif stripped.startswith("# "):
            html_lines.append(f"<h1>{stripped[2:]}</h1>")
        elif stripped.startswith("|"):
            continue  # tables skipped, same tradeoff as the DOCX/PDF export
        else:
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", stripped)
            text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
            html_lines.append(f"<p>{text}</p>")
    return "\n".join(html_lines)


def publish_post(*, title: str, article_markdown: str, excerpt: str = "", slug: str = "",
                  status: str = "draft", dry_run: bool = False) -> dict:
    """Publishes (or, if dry_run, simulates publishing) an article to
    WordPress as a post. status is 'draft' by default — 'publish' must be
    explicitly requested by the caller, it is never the implicit default."""
    payload = {
        "title": title,
        "content": _markdown_to_basic_html(article_markdown),
        "status": status,
        "excerpt": excerpt,
        "slug": slug,
    }

    if dry_run:
        return {"success": True, "dry_run": True, "would_send": payload, "post_id": None, "post_url": None, "error": None}

    if not is_configured():
        return {"success": False, "error": "WordPress is not configured — set WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD."}

    url = f"{settings.WORDPRESS_URL}/wp-json/wp/v2/posts"
    try:
        resp = requests.post(url, auth=_auth(), json=payload, timeout=settings.WORDPRESS_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        logger.error("WordPress publish failed: %s", e)
        return {"success": False, "error": _friendly_error(e)}

    if resp.status_code in (200, 201):
        try:
            data = resp.json()
        except ValueError:
            return {"success": False, "error": "WordPress accepted the request but returned an unexpected (non-JSON) response."}
        return {"success": True, "post_id": data.get("id"), "post_url": data.get("link"), "status": data.get("status"), "error": None}

    if resp.status_code in (401, 403):
        return {"success": False, "error": "Authentication failed — check WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD."}

    try:
        err_body = resp.json()
        message = err_body.get("message", f"HTTP {resp.status_code}")
    except ValueError:
        message = f"HTTP {resp.status_code}"
    return {"success": False, "error": f"WordPress rejected the post: {message}"}
