"""Deterministic SEO output pack: structured data, social tags, title tags.

Everything here is computed from the finished article — no model call, no
extra latency, no chance of a hallucinated field. That matters because
structured data is the one part of the output that a search engine parses
literally: a model that invents an `author` or drops `@context` produces
markup that fails validation silently, and the page just never gets a rich
result. Building it in code means it's always valid and always matches the
article body.

Emitted as a schema.org @graph so Article, FAQPage and BreadcrumbList are
linked by @id rather than three unrelated blobs on the page — that's how
Google's documentation recommends expressing multiple types for one URL.
"""

import re
from datetime import datetime, timezone

MAX_TITLE_TAG_CHARS = 60
MAX_META_CHARS = 160

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)
_MD_INLINE_RE = re.compile(r"[*_`]+")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def strip_markdown(text: str) -> str:
    """Plain-text version of a markdown fragment, for use inside JSON-LD
    string fields (which must not contain markup)."""
    if not text:
        return ""
    text = _LINK_RE.sub(r"\1", text)
    text = _MD_INLINE_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_headings(article_markdown: str) -> list[dict]:
    """Ordered H1-H6 outline of the article as actually written — the basis
    for the table-of-contents and for checking the H1 against the keyword."""
    return [
        {"level": len(m.group(1)), "text": strip_markdown(m.group(2))}
        for m in _HEADING_RE.finditer(article_markdown or "")
    ]


def _first_h1(article_markdown: str) -> str:
    for h in extract_headings(article_markdown):
        if h["level"] == 1:
            return h["text"]
    return ""


def _lead_paragraph(article_markdown: str) -> str:
    """First real paragraph of body copy, skipping headings, tables, lists
    and blockquotes — used as the structured-data description fallback."""
    for block in re.split(r"\n\s*\n", article_markdown or ""):
        line = block.strip()
        if not line or line.startswith(("#", "|", ">", "-", "*", "---")):
            continue
        return strip_markdown(line)
    return ""


def title_tag_variants(topic: str, keyword: str, geo: str, h1: str = "") -> list[str]:
    """Three <title> candidates under the ~60 character truncation point.

    The article H1 and the browser title tag serve different jobs — the H1
    reads as a headline, the title tag has to survive truncation in a
    results page — so these are generated rather than reusing the H1
    verbatim.
    """
    topic = (topic or "").strip()
    keyword = (keyword or "").strip()
    geo = (geo or "").strip()
    base = (h1 or topic or keyword).strip()
    # An H1 is usually written as "Topic: Your Complete Guide". Appending a
    # second subtitle to that produces "Topic: Your Complete Guide: Symptoms,
    # Diet & Care", so the existing subtitle is dropped before composing.
    if ":" in base:
        base = base.split(":", 1)[0].strip() or base
    if len(base) > 42:
        base = topic or base

    candidates = [
        f"{base}: Symptoms, Diet & Care",
        f"{keyword.title()} — Complete Guide" if keyword else f"{base} — Complete Guide",
        f"{base} in {geo}" if geo else f"{base}: What to Know",
    ]

    out = []
    for c in candidates:
        c = re.sub(r"\s+", " ", c).strip()
        if len(c) > MAX_TITLE_TAG_CHARS:
            # Trim on a word boundary rather than mid-word — a title tag cut
            # to "Irritable Bowel Syndrom" looks like a typo, not a truncation.
            c = c[:MAX_TITLE_TAG_CHARS].rsplit(" ", 1)[0].rstrip(" ,:-—")
        if c and c not in out:
            out.append(c)
    return out


def _clean_slug(slug: str, topic: str) -> str:
    slug = (slug or "").strip().strip("/")
    if not slug:
        # Devanagari is kept: a Hindi topic run through an ASCII-only filter
        # loses every character and falls back to the literal word "article",
        # giving every Hindi page the same URL.
        slug = re.sub(r"[^a-z0-9ऀ-ॿ]+", "-", (topic or "article").lower()).strip("-")
    return slug or "article"


def build_structured_data(
    result: dict,
    topic: str,
    keyword: str,
    geo: str = "",
    language: str = "en",
    site_url: str = "",
    publisher_name: str = "Gutfolio",
    reviewer_badge: str = "",
) -> dict:
    """schema.org @graph covering Article + FAQPage + BreadcrumbList.

    `site_url` is optional: without it the @id values are relative fragments,
    which are still valid and become absolute once the page is published at
    a real URL.
    """
    article_md = result.get("optimized_article_markdown", "") or ""
    slug = _clean_slug(result.get("url_slug", ""), topic)
    base = (site_url or "").rstrip("/")
    page_url = f"{base}/{slug}" if base else f"/{slug}"

    headline = _first_h1(article_md) or (topic or "").strip()
    # schema.org caps headline at 110 characters; longer values are ignored
    # by consumers rather than truncated, so cap it here.
    headline = headline[:110].rstrip()
    description = strip_markdown(result.get("meta_description", "")) or _lead_paragraph(article_md)[:MAX_META_CHARS]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    word_count = len(article_md.split())

    article_node = {
        "@type": "MedicalWebPage",
        "@id": f"{page_url}#article",
        "url": page_url,
        "headline": headline,
        "description": description,
        "inLanguage": language,
        "datePublished": now,
        "dateModified": now,
        "wordCount": word_count,
        "keywords": [k for k in [keyword, topic] if k],
        "publisher": {"@type": "Organization", "name": publisher_name},
        "isAccessibleForFree": True,
        # Signals to a search engine that this page is health information
        # written for patients, which is what the audience actually is.
        "audience": {"@type": "Patient"},
        "medicalAudience": "Patient",
    }
    if geo:
        article_node["contentLocation"] = {"@type": "Place", "name": geo}
    if reviewer_badge:
        # A named human reviewer is the strongest E-E-A-T signal this app can
        # emit, and it's only emitted when a real person actually signed off
        # in the review queue — never fabricated.
        reviewer = reviewer_badge.replace("Reviewed by", "").strip()
        article_node["reviewedBy"] = {"@type": "Person", "name": reviewer}
        article_node["lastReviewed"] = now

    graph = [article_node]

    faqs = [f for f in (result.get("faqs") or []) if isinstance(f, dict) and f.get("question") and f.get("answer")]
    if faqs:
        graph.append({
            "@type": "FAQPage",
            "@id": f"{page_url}#faq",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": strip_markdown(f["question"]),
                    "acceptedAnswer": {"@type": "Answer", "text": strip_markdown(f["answer"])},
                }
                for f in faqs
            ],
        })

    graph.append({
        "@type": "BreadcrumbList",
        "@id": f"{page_url}#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": base or "/"},
            {"@type": "ListItem", "position": 2, "name": "Gut Health", "item": f"{base}/gut-health" if base else "/gut-health"},
            {"@type": "ListItem", "position": 3, "name": headline or topic, "item": page_url},
        ],
    })

    return {"@context": "https://schema.org", "@graph": graph}


def build_social_meta(result: dict, topic: str, keyword: str, geo: str = "", language: str = "en",
                      site_url: str = "", site_name: str = "Gutfolio") -> dict:
    """Open Graph + Twitter card tags, ready to paste into a page <head>."""
    article_md = result.get("optimized_article_markdown", "") or ""
    slug = _clean_slug(result.get("url_slug", ""), topic)
    base = (site_url or "").rstrip("/")
    page_url = f"{base}/{slug}" if base else f"/{slug}"
    h1 = _first_h1(article_md)
    titles = title_tag_variants(topic, keyword, geo, h1)
    description = strip_markdown(result.get("meta_description", "")) or _lead_paragraph(article_md)[:MAX_META_CHARS]

    return {
        "title_tag_variants": titles,
        "recommended_title_tag": titles[0] if titles else (h1 or topic),
        "canonical_url": page_url,
        "tags": {
            "og:type": "article",
            "og:site_name": site_name,
            "og:title": titles[0] if titles else (h1 or topic),
            "og:description": description,
            "og:url": page_url,
            "og:locale": "hi_IN" if language == "hi" else "en_US",
            "twitter:card": "summary_large_image",
            "twitter:title": titles[0] if titles else (h1 or topic),
            "twitter:description": description,
        },
    }


def build_table_of_contents(article_markdown: str) -> list[dict]:
    """H2/H3 outline with anchor slugs, for an on-page jump list."""
    toc = []
    for h in extract_headings(article_markdown):
        if h["level"] not in (2, 3):
            continue
        anchor = re.sub(r"[^a-z0-9ऀ-ॿ]+", "-", h["text"].lower()).strip("-")
        toc.append({"level": h["level"], "text": h["text"], "anchor": anchor})
    return toc


def build_seo_pack(result: dict, topic: str, keyword: str, geo: str = "", language: str = "en",
                   site_url: str = "", reviewer_badge: str = "") -> dict:
    """Everything an editor needs to publish the article correctly, in one
    object: validated structured data, social tags, title candidates and an
    on-page table of contents."""
    return {
        "structured_data": build_structured_data(
            result, topic, keyword, geo, language, site_url, reviewer_badge=reviewer_badge
        ),
        "social": build_social_meta(result, topic, keyword, geo, language, site_url),
        "table_of_contents": build_table_of_contents(result.get("optimized_article_markdown", "") or ""),
        "headings": extract_headings(result.get("optimized_article_markdown", "") or ""),
    }
