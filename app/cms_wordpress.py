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

import html
import logging
import re

import requests

from app.config import settings

logger = logging.getLogger("gutfolio.wordpress")

_NOT_CONFIGURED = "WordPress is not configured — set WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD."
_AUTH_FAILED = "Authentication failed — check WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD."


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
        return {"connected": False, "error": _NOT_CONFIGURED}

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
        return {"connected": False, "error": _AUTH_FAILED}
    if resp.status_code == 404:
        return {
            "connected": False,
            "error": f"WordPress REST API not found at {url} — check WORDPRESS_URL and that the REST API is enabled.",
        }
    return {"connected": False, "error": f"WordPress returned HTTP {resp.status_code}."}


_SAFE_URL = re.compile(r"^(https?://|/|#|mailto:)", re.IGNORECASE)
_TABLE_DIVIDER = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")
_RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})$")


def _inline(text: str) -> str:
    """Escapes first, then adds a fixed set of tags — the same construction
    as the in-app renderer (static/ui.js). Model output is untrusted: the old
    converter copied it into the post body verbatim, so an `<img onerror=...>`
    in an article became live markup on the WordPress site (administrators
    have unfiltered_html, so WordPress does not strip it for them)."""
    out = html.escape(text, quote=True)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)

    def link(match):
        label, url = match.group(1), html.unescape(match.group(2))
        if _SAFE_URL.match(url):
            return f'<a href="{html.escape(url, quote=True)}">{label}</a>'
        return label  # javascript:, data: and friends lose the link, keep the text

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(^|[\s(])\*([^*\n]+)\*", r"\1<em>\2</em>", out)
    out = re.sub(r"(^|[\s(])_([^_\n]+)_", r"\1<em>\2</em>", out)
    return out


def _table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_block_start(lines: list[str], i: int) -> bool:
    s = lines[i].strip()
    return bool(
        not s or s.startswith(("```", ">")) or _HEADING.match(s) or _RULE.match(s)
        or _BULLET.match(s) or _NUMBERED.match(s)
        or (s.startswith("|") and i + 1 < len(lines) and _TABLE_DIVIDER.match(lines[i + 1].strip()))
    )


def _markdown_to_basic_html(markdown_text: str) -> str:
    """Dependency-free markdown -> HTML for WordPress post content: headings,
    paragraphs, bullet and numbered lists, tables, blockquotes, rules, code,
    links and bold/italic. Everything is HTML-escaped before tags are added.

    Lists and tables used to come out as "<p>- item</p>" or not at all,
    which dropped the comparison tables and step lists that carry most of
    an article's practical value."""
    lines = (markdown_text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue

        if s.startswith("```"):
            body = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(body))}</code></pre>")
            continue

        heading = _HEADING.match(s)
        if heading:
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            i += 1
            continue

        if _RULE.match(s):
            out.append("<hr>")
            i += 1
            continue

        if s.startswith("|") and i + 1 < len(lines) and _TABLE_DIVIDER.match(lines[i + 1].strip()):
            header = _table_row(s)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_table_row(lines[i]))
                i += 1
            head_html = "".join(f"<th>{_inline(c)}</th>" for c in header)
            body_html = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in row) + "</tr>" for row in rows
            )
            out.append(f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>")
            continue

        if _BULLET.match(s) or _NUMBERED.match(s):
            marker = _BULLET if _BULLET.match(s) else _NUMBERED
            tag = "ul" if marker is _BULLET else "ol"
            items = []
            while i < len(lines) and marker.match(lines[i]):
                items.append(marker.sub("", lines[i], count=1).strip())
                i += 1
            out.append(f"<{tag}>" + "".join(f"<li>{_inline(item)}</li>" for item in items) + f"</{tag}>")
            continue

        if s.startswith(">"):
            quoted = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote><p>{_inline(' '.join(q for q in quoted if q))}</p></blockquote>")
            continue

        paragraph = [s]
        i += 1
        while i < len(lines) and not _is_block_start(lines, i):
            paragraph.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(paragraph))}</p>")
    return "\n".join(out)


def publish_post(*, title: str, article_markdown: str, excerpt: str = "", slug: str = "",
                  status: str = "draft", dry_run: bool = False, post_id: int | None = None) -> dict:
    """Publishes (or, if dry_run, simulates publishing) an article to
    WordPress as a post. status is 'draft' by default — 'publish' must be
    explicitly requested by the caller, it is never the implicit default.

    With post_id, the existing post is updated in place (WP REST
    POST /posts/<id>) instead of a new one being created. If that post no
    longer exists on the site (deleted in WP admin), a new one is created."""
    payload = {
        "title": title,
        "content": _markdown_to_basic_html(article_markdown),
        "status": status,
        # The excerpt is model output too; themes print it as HTML.
        "excerpt": html.escape(excerpt or "", quote=False),
        "slug": slug,
    }

    if dry_run:
        return {"success": True, "dry_run": True, "would_send": payload, "post_id": post_id,
                "post_url": None, "updates_existing": post_id is not None, "error": None}

    if not is_configured():
        return {"success": False, "error": _NOT_CONFIGURED}

    url = f"{settings.WORDPRESS_URL}/wp-json/wp/v2/posts"
    if post_id is not None:
        url = f"{url}/{int(post_id)}"
    try:
        resp = requests.post(url, auth=_auth(), json=payload, timeout=settings.WORDPRESS_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException as e:
        logger.error("WordPress publish failed: %s", e)
        return {"success": False, "error": _friendly_error(e)}

    if post_id is not None and resp.status_code in (404, 410):
        logger.warning("WordPress post %s no longer exists; creating a new post instead", post_id)
        return publish_post(title=title, article_markdown=article_markdown, excerpt=excerpt,
                            slug=slug, status=status, dry_run=False, post_id=None)

    if resp.status_code in (200, 201):
        try:
            data = resp.json()
        except ValueError:
            return {
                "success": False,
                "error": "WordPress accepted the request but returned an unexpected (non-JSON) response.",
            }
        return {"success": True, "post_id": data.get("id"), "post_url": data.get("link"), "status": data.get("status"),
                "updated_existing": post_id is not None, "error": None}

    if resp.status_code in (401, 403):
        return {"success": False, "error": _AUTH_FAILED}

    try:
        err_body = resp.json()
        message = err_body.get("message", f"HTTP {resp.status_code}")
    except ValueError:
        message = f"HTTP {resp.status_code}"
    return {"success": False, "error": f"WordPress rejected the post: {message}"}
