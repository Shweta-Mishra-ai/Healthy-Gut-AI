<div align="center">

# 🥗 Healthy Gut AI

**Production-grade AI content engine for medically-grounded, SEO-optimized gut health articles.**

[![CI](https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Groq](https://img.shields.io/badge/LLM-Groq%20%2F%20Llama%203.3-orange)](https://console.groq.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-143%20passing-brightgreen)](tests/)

[Quick Start](#-quick-start) · [Architecture](#-architecture) · [API Reference](#-api-reference) · [Deployment](#-deployment) · [Contributing](CONTRIBUTING.md)

</div>

---

## Overview

Healthy Gut AI takes a topic, a primary keyword, and a geo-target, and returns
a medically-grounded, SEO-structured article — complete with meta description,
URL slug, FAQs, JSON-LD schema, and quality metrics — in one request.

It's built the way a production content pipeline should be, not the way a
demo usually is:

- **No single point of failure.** A three-provider LLM fallback chain (two of
  them free) means one API outage never takes the app down.
- **Fails safely, not silently.** Structured error codes, not generic 500s.
- **Costs nothing to run at small scale.** Default provider is Groq's free
  tier; OpenAI is an optional, last-resort fallback you control.
- **Tested, not just written.** 143 automated tests, CI on every push.

<p align="center">
  <img src="docs/pipeline-flow.gif" alt="Healthy Gut AI request pipeline animation" width="800">
</p>

---

## ✨ Features

| Category | Capability |
|---|---|
| **Generation** | Single-article and batch (multi-topic, bounded-concurrency) generation |
| **Topic scoping** | Rejects clearly out-of-scope topics (e.g. "infectious disease epidemiology") with a clear 422 instead of generating unfocused, off-topic content |
| **Length compliance** | Prompts use per-section word budgets (not a single vague target) for more reliable pillar/supporting length adherence; actual word count is surfaced in every response |
| **Quality scoring** | Every article gets a programmatic 0-100 score with specific flags (word count vs. target, keyword placement, meta description length, slug format, FAQ count, readability band, disclaimer presence, **language-script purity for non-English requests**) — not a self-reported LLM claim |
| **Human review** | Every article starts as a `draft`; a reviewer must explicitly approve or reject it (`/review` page) before it's considered publish-ready — no article ships without a human checking the medical framing |
| **Reviewer credential badge** | Approving an article can optionally attach a reviewer name + credential (e.g. "Dr. Anita Rao, MBBS, RMP") — self-attested, same trust model as Healthline/WebMD editorial review. Stored, shown in the review queue, and appended to the article when publishing to WordPress |
| **Persistence** | Review history and dashboard data are stored in SQLite (`app/db.py`), surviving process restarts on hosts with real disks — see caveat below for ephemeral-disk hosts like Render's free tier |
| **Internal linking** | Every new article gets TF-IDF-ranked suggestions to link to previously **approved** articles (`internal_link_suggestions`), for SEO cluster building — drafts/rejected articles are never suggested |
| **WordPress publishing** | Optional REST API integration (`app/cms_wordpress.py`) — publishes **approved** articles only, as WordPress drafts by default, with a dry-run mode to preview the exact payload before any real site is configured |
| **Reliability** | Groq → OpenRouter → OpenAI → Mock fallback chain, each with retry + backoff + timeout |
| **Validation** | Strict Pydantic schemas — length limits, empty/whitespace rejection, unsafe-character rejection |
| **Rate limiting** | Per-IP sliding-window limiter, configurable via `RATE_LIMIT_PER_MINUTE` |
| **Caching** | In-memory TTL cache — identical requests skip the LLM call entirely |
| **Security** | DOMPurify-sanitized markdown rendering on the frontend (XSS-safe) |
| **Localization** | English and Hindi article generation — mock mode has a fully separate Hindi template (no English leakage); live LLM prompts explicitly require full-language translation of any injected context; a programmatic quality check flags mixed-language output if it happens anyway |
| **RAG retrieval** | TF-IDF similarity search over a 24-topic curated gut-health knowledge base — real relevance ranking, not keyword lookup; `/rag/preview` exposes matches + scores |
| **Export** | Download generated articles as `.docx` or `.pdf` |
| **Quality metrics** | Flesch Reading Ease + keyword density on every article |
| **SEO metadata** | Meta description (3 A/B-testable variants — benefit-led, question-led, keyword-led), URL slug, FAQs, `schema.org` JSON-LD, dual CTAs |
| **Observability** | Structured request logging, `/health` reports live provider config + cache stats |
| **Deployability** | Railway (`Procfile`) and Vercel/AWS Lambda (`api/index.py` via Mangum) out of the box |

---

## 🏗 Architecture

<p align="center">
  <img src="docs/architecture.svg" alt="Healthy Gut AI architecture diagram" width="900">
</p>

### Request pipeline (flowchart)

```mermaid
flowchart LR
    A[Client] --> B[Rate Limiter\nper-IP sliding window]
    B -- 429 if exceeded --> A
    B --> C[Validation\nPydantic schemas]
    C -- 422 on bad input --> A
    C --> D{Cache hit?}
    D -- yes --> H[Metrics engine]
    D -- no --> E[LLM Fallback Chain]
    E --> H
    H --> I[Response\nJSON / DOCX / PDF]
    E -.write-back.-> D

    subgraph E[LLM Fallback Chain]
        direction TB
        E1[1. Groq — Llama 3.3 70B] -->|on failure| E2[2. OpenRouter — free tier]
        E2 -->|on failure| E3[3. OpenAI — gpt-4o-mini optional]
        E3 -->|on failure| E4[4. Mock template — always succeeds]
    end
```

### Request lifecycle (sequence)

```mermaid
sequenceDiagram
    participant U as Client
    participant API as FastAPI
    participant RL as Rate Limiter
    participant V as Validator
    participant C as TTL Cache
    participant L as LLM Chain
    participant M as Metrics

    U->>API: POST /generate
    API->>RL: check(ip)
    alt over limit
        RL-->>U: 429 Too Many Requests
    else within limit
        RL->>V: validate(payload)
        alt invalid input
            V-->>U: 422 Validation Failed
        else valid
            V->>C: get(hash(topic,keyword,geo,type,lang))
            alt cache hit
                C-->>M: cached article
            else cache miss
                C->>L: generate()
                L->>L: try Groq → OpenRouter → OpenAI → Mock
                L-->>C: article JSON
                C->>C: store(ttl)
            end
            C->>M: compute readability + keyword density
            M-->>U: 200 OK + article + metrics
        end
    end
```

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| LLM providers | Groq (free), OpenRouter (free tier), OpenAI (optional) — via OpenAI-compatible client |
| Validation | Pydantic v2 |
| Frontend | Vanilla JS, Marked.js (markdown render), DOMPurify (sanitization), CSS glassmorphism |
| Export | `python-docx`, `fpdf2` |
| Testing | pytest, httpx, FastAPI `TestClient` |
| CI/CD | GitHub Actions |
| Deployment | Railway (`Procfile`) · Vercel/AWS Lambda (`Mangum`) |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or 3.12
- (Optional but recommended) A free [Groq API key](https://console.groq.com)

### 1. Clone and install

```bash
git clone https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI.git
cd Healthy-Gut-AI
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` — at minimum:

```env
GROQ_API_KEY=gsk_your_key_here
```

> No key set? The app runs in **mock mode** automatically — fully functional
> for local development and demos, zero cost, zero setup.

### 3. Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000**.

### 4. Verify it's healthy

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "mode": "live",
  "providers_configured": { "groq": true, "openrouter": false, "openai": false },
  "cache": { "entries": 0, "max_entries": 500, "ttl_seconds": 3600 }
}
```

---

## 🔑 Environment Variables

Full reference in [`.env.example`](.env.example).

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | No* | — | Primary LLM provider, free tier |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model name |
| `OPENROUTER_API_KEY` | No* | — | Free-tier fallback if Groq is unavailable |
| `OPENROUTER_MODEL` | No | `meta-llama/llama-3.3-70b-instruct:free` | OpenRouter model name |
| `OPENAI_API_KEY` | No | — | Optional paid last-resort fallback |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model name |
| `LLM_TIMEOUT_SECONDS` | No | `45` | Per-attempt timeout |
| `LLM_MAX_RETRIES` | No | `2` | Retries per provider before falling through |
| `RATE_LIMIT_PER_MINUTE` | No | `10` | Requests per IP per minute on `/generate*` |
| `CACHE_TTL_SECONDS` | No | `3600` | How long identical requests are served from cache |
| `MAX_BATCH_SIZE` | No | `10` | Max items per `/generate/batch` call |
| `BATCH_CONCURRENCY` | No | `3` | Concurrent LLM calls within a batch |
| `API_KEY` | No | — | If set, requires `X-API-Key` header on `/generate*`, `/export/*`, `/debug` |
| `DATABASE_PATH` | No | `healthy_gut_ai.db` | SQLite file for review history + dashboard data (see ephemeral-disk caveat) |
| `WORDPRESS_URL` | No | — | WordPress site URL for publishing (e.g. `https://yoursite.com`) |
| `WORDPRESS_USERNAME` | No | — | WordPress username (existing account, no new one needed) |
| `WORDPRESS_APP_PASSWORD` | No | — | Application Password from WP admin (Users > Profile) — not the login password |
| `WORDPRESS_TIMEOUT_SECONDS` | No | `15` | Request timeout for WordPress API calls |

*No provider key is required — the app runs in mock mode without any of them.*

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Frontend UI |
| `GET` | `/health` | Status, active mode, provider config, cache stats |
| `GET` | `/debug` | Lists all registered routes |
| `GET` | `/rag/preview?topic=...&keyword=...` | Shows which knowledge-base chunks are retrieved for a query, with similarity scores |
| `GET` | `/outline?topic=...&keyword=...&article_type=...` | Deterministic outline preview (no LLM call) — planned sections, word budgets, scope check, grounding sources |
| `POST` | `/export/markdown` | Generate (or reuse cache) and return raw `.md` |
| `POST` | `/export/json` | Generate (or reuse cache) and return the full result object as `.json` |
| `GET` | `/dashboard` | HTML dashboard — generation history, quality trends, provider breakdown |
| `GET` | `/dashboard/stats` | JSON dashboard data (same source as the HTML page) |
| `GET` | `/review` | HTML review queue — approve/reject drafts |
| `GET` | `/review/counts` | Draft/approved/rejected counts |
| `GET` | `/review/queue?status=draft` | List articles by review status |
| `GET` | `/review/{id}` | Fetch one article's full review record |
| `POST` | `/review/{id}/approve` | Approve a draft (one-way — 409 if already reviewed) |
| `POST` | `/review/{id}/reject` | Reject a draft (one-way — 409 if already reviewed) |
| `GET` | `/internal-links?topic=...&keyword=...` | Ad-hoc query for related **approved** articles to link to (SEO cluster building) |
| `GET` | `/publish/wordpress/status` | Whether WordPress publishing is configured |
| `POST` | `/publish/wordpress/test-connection` | Verifies configured WordPress credentials work (read-only, safe to call anytime) |
| `POST` | `/publish/wordpress/{id}?status=draft&dry_run=false` | Publishes an **approved** article to WordPress (409 if not approved); `dry_run=true` previews the payload without sending it |
| `POST` | `/generate` | Generate one article |
| `POST` | `/generate/batch` | Generate up to `MAX_BATCH_SIZE` articles concurrently |
| `POST` | `/export/batch/zip` | Generate (or reuse cache for) a batch and return one ZIP: `.docx` per article + `batch_summary.csv` |
| `POST` | `/export/docx` | Generate (or reuse cache) and return as `.docx` |
| `POST` | `/export/pdf` | Generate (or reuse cache) and return as `.pdf` |

### `POST /generate`

**Request**

```json
{
  "topic": "IBS diet plan",
  "primary_keyword": "IBS diet",
  "geo_target": "India",
  "article_type": "supporting",
  "language": "en"
}
```

**Response — `200 OK`**

```json
{
  "optimized_article_markdown": "# IBS Diet Plan...",
  "meta_description": "Learn about IBS diet with our expert guide...",
  "url_slug": "ibs-diet-plan-guide",
  "faqs": [{ "question": "...", "answer": "..." }],
  "schema_json_ld": { "@context": "https://schema.org", "@type": "Article" },
  "cta_soft": "Explore more free gut health resources...",
  "cta_direct": "Try Healthy Gut AI FREE today...",
  "provider_used": "groq",
  "cached": false,
  "metrics": {
    "readability": { "fleschReadingEase": 62.4 },
    "keywordDensity": { "totalWords": 940, "keywordCount": 12, "keywordDensityPercent": 1.28 }
  }
}
```

**Error responses**

| Status | Meaning |
|---|---|
| `422` | Validation failed — see `details` array for field-level errors |
| `429` | Rate limit exceeded — see `retry_after_seconds` |
| `502` | All LLM providers failed for this request |
| `500` | Unexpected server error |

### `POST /generate/batch`

```json
{ "items": [ { "topic": "...", "primary_keyword": "...", "geo_target": "..." } ] }
```

Returns `{ "results": [...], "total": N, "succeeded": N, "failed": N }` — a
failure in one item never fails the whole batch.

---

## 🧪 Testing

```bash
python -m pytest tests/ -v
```

125 tests across thirteen suites (including cache, config, and export unit tests):

| Suite | Covers |
|---|---|
| `tests/test_metrics.py` | Readability/keyword-density edge cases (empty text, empty keyword, multi-word keywords) |
| `tests/test_cache.py` | TTL cache set/get, max-entries eviction, expiration |
| `tests/test_config.py` | Settings load correctly from environment variables |
| `tests/test_exports.py` | DOCX/PDF byte-level conversion sanity checks |
| `tests/test_schemas.py` | Input validation (length limits, unsafe characters, batch size limits) |
| `tests/test_rag.py` | Retrieval quality — relevant queries rank the correct topic first, different queries return different results, empty/nonsense queries fall back gracefully |
| `tests/test_security.py` | Optional API-key auth (blocked/allowed), disclaimer safety-net (always present, appended if missing, not duplicated) |
| `tests/test_scope_and_batch_export.py` | Topic-scope guard (in/out of domain), batch ZIP export contents (DOCX files + CSV, including failed-item rows) |
| `tests/test_quality.py` | Programmatic quality scoring — word count, keyword placement, meta length, slug format, FAQ count, readability band, disclaimer presence |
| `tests/test_load.py` | Concurrent requests don't crash the app, bounded batch concurrency completes reliably, rate limiter is a real recoverable sliding window, concurrent review actions don't double-approve, concurrent SQLite writes don't corrupt/lose data |
| `tests/test_reviewer_badge.py` | Reviewer credential badge — storage, computed badge text, validation, WordPress publish integration |
| `tests/test_phase2_phase3.py` | Outline preview (in/out of scope), tone field validation, JSON/Markdown export, in-article references section, extended readability metrics, dashboard stats/page |
| `tests/test_review.py` | Review workflow — draft registration, queue listing/filtering, approve/reject, 404 on missing article, 409 on double-review, note validation, cache-hit review-id reuse |
| `tests/test_meta_variants.py` | A/B meta description variants — mock generation, safety-net fallback when the provider skips the field, quality-flag behavior for too-few/wrong-length variants |
| `tests/test_internal_linking.py` | Internal link suggestions — empty corpus, similarity ranking, drafts/rejected articles excluded, self-exclusion, endpoint validation |
| `tests/test_wordpress_publish.py` | WordPress publishing — mocked HTTP for success/auth-failure/connection-error/timeout/rejection, dry-run mode, approved-only business rule (409 for draft/rejected), markdown→HTML conversion |
| `tests/test_api.py` | Full request lifecycle in mock mode — health, generation, caching, batching, rate limiting |

CI (`.github/workflows/ci.yml`) runs the full suite on Python 3.11 and 3.12
on every push and pull request.

---

## 📦 Project Structure

```
Healthy-Gut-AI/
├── app/
│   ├── main.py            # App assembly: middleware, exception handlers, health/debug/root, router registration
│   ├── routers/
│   │   ├── generation.py    # /generate, /generate/batch, /export/*
│   │   ├── discovery.py     # /rag/preview, /outline, /internal-links (free, no LLM cost)
│   │   ├── review.py        # /review*, /dashboard* (draft/approve/reject workflow)
│   │   └── publish.py       # /publish/wordpress*
│   ├── constants.py        # Shared constants (STATIC_DIR, OUT_OF_SCOPE_MESSAGE)
│   ├── config.py          # Environment-driven settings
│   ├── schemas.py          # Pydantic request/response models
│   ├── llm_providers.py    # Groq → OpenRouter → OpenAI → Mock fallback chain
│   ├── metrics.py          # Readability + keyword density
│   ├── cache.py             # In-memory TTL cache
│   ├── rate_limit.py        # In-memory sliding-window limiter
│   ├── export.py            # DOCX / PDF generation
│   ├── quality.py           # Programmatic article quality scoring
│   ├── review.py            # Human review workflow (draft/approve/reject), SQLite-backed
│   ├── dashboard.py         # Generation history tracker, SQLite-backed
│   ├── db.py                # SQLite connection + schema (shared by review.py, dashboard.py)
│   ├── internal_linking.py  # TF-IDF-ranked internal link suggestions over approved articles
│   ├── cms_wordpress.py     # Optional WordPress REST API publishing (approved-only, draft-by-default)
│   └── rag/
│       ├── knowledge_base.py  # 24-topic curated gut-health corpus
│       └── retriever.py       # TF-IDF similarity retrieval
├── api/
│   └── index.py             # Mangum wrapper for Vercel/AWS Lambda
├── static/                  # Frontend (HTML/CSS/JS)
├── tests/                   # pytest suite
├── docs/
│   ├── architecture.svg     # Full pipeline diagram
│   └── pipeline-flow.gif    # Animated request-lifecycle illustration
├── prompts/                 # Reference prompt templates
├── .github/workflows/ci.yml
├── requirements.txt
├── Procfile                 # Railway deployment
├── .env.example
├── CONTRIBUTING.md
└── LICENSE
```

---

## 🌐 Deployment

### Render (primary — see `render.yaml`)

1. Push to GitHub, connect the repo in Render as a new Web Service.
2. Render auto-detects `render.yaml` (build/start commands, default env vars).
3. Add secrets manually in the Render dashboard: `GROQ_API_KEY` at minimum.

### Railway

1. Push to GitHub, connect the repo in Railway.
2. Set environment variables (at minimum `GROQ_API_KEY`) under **Variables**.
3. Railway auto-detects `Procfile` — no further config needed.

### Vercel / AWS Lambda

`api/index.py` wraps the FastAPI app with [Mangum](https://mangum.io/) for
serverless execution — deploy as-is on Vercel's Python runtime or package for
Lambda.

---

## ⚠️ Known Limitations

Documented honestly rather than hidden:

- **Codebase is organized into routers** (`app/routers/`) rather than one
  large `main.py` — this split was verified by the full test suite plus a
  live smoke test, which caught a real regression: `/debug` crashed after
  the split because FastAPI's newer `include_router()` wraps sub-router
  routes in a way that doesn't expose `.path` uniformly on `app.routes`.
  Fixed with a recursive route-path collector; `/debug` had zero test
  coverage before, which is why it slipped through — it's covered now.
- **Cache and rate limiter are still in-memory** — reset on restart, not
  shared across workers/dynos. Review history and dashboard data now use
  SQLite (`app/db.py`) instead, but see the next point for what that does
  and doesn't guarantee.
- **SQLite persistence depends on the host's disk being real, not ephemeral**
  — on Render's free tier (and similar), the filesystem resets on every
  spin-down/redeploy, so `healthy_gut_ai.db` is wiped just like the old
  in-memory stores were. It survives fine across multiple requests within
  one running instance (which is most of the practical benefit — the app
  no longer forgets everything between two requests seconds apart). True
  persistence across restarts needs either a paid plan with an attached
  disk, or pointing `DATABASE_PATH`/swapping in a hosted DB (Postgres,
  Turso, etc.) — the interfaces in `app/review.py` and `app/dashboard.py`
  were kept identical to the old in-memory versions specifically so that
  swap wouldn't require touching `app/main.py`.
- **API-key auth is optional and off by default** — set `API_KEY` before
  exposing this publicly at any real scale; without it, anyone with the URL
  can generate articles up to the rate limit. Once set, `/generate*`,
  `/export/*`, and `/debug` all require an `X-API-Key` header.
- **DOCX/PDF export skip markdown tables** rather than mis-rendering them —
  a dedicated table renderer is a good next contribution.
- **RAG uses TF-IDF, not neural embeddings** — a deliberate tradeoff for a
  24-chunk corpus (no `torch`/vector-DB dependency, fast to install and run
  anywhere). Real relevance ranking, not keyword matching — see `/rag/preview`
  to inspect it — but if the knowledge base grows past a few hundred chunks,
  swap in `sentence-transformers` + Chroma/pgvector; `build_rag_context()`'s
  interface won't need to change for callers.
- **Knowledge base is 24 topics** (IBS, IBD, GERD, Celiac, SIBO, microbiome,
  FODMAP, and more) — solid coverage for common gut-health content, but
  narrower/rarer conditions will fall back to the closest general match
  rather than a perfect one. Add chunks in `app/rag/knowledge_base.py`
  (no retriever code changes needed).
- **Hindi articles previously leaked raw English RAG context** — fixed:
  mock mode's Hindi template no longer embeds the (English) knowledge-base
  paragraph or FAQ answer verbatim; live-provider prompts now explicitly
  require translating any injected context and reinforce this in both the
  drafting and SEO-optimization passes. Since prompting can't 100%
  guarantee this for live LLM output, `app/quality.py` also measures actual
  Devanagari-script purity of the result and flags anything below 50% as
  likely mixed-language — a verifiable check, not just a prompt hope.
  Citation titles in the auto-appended Sources section are exempt (English
  proper nouns there are expected and normal).
- **WordPress publishing was verified with mocked HTTP calls, not a live site**
  — no WordPress instance was available during development. Every response
  path (success, auth failure, connection error, timeout, WP-side rejection)
  is tested against a mocked `requests` call, and `dry_run=true` lets you
  inspect the exact payload before ever configuring a real site. Run
  `POST /publish/wordpress/test-connection` against your actual site before
  depending on this in production.
- **Cache hits self-heal a missing review_id** — if a cached article's
  review-workflow entry has been evicted (or storage was reset) since it was
  cached, `_generate_one()` re-registers a fresh draft rather than returning
  a `review_id` that would 404 on every approve/reject/publish call. This was
  a real bug caught by the test suite (test isolation surfaced a dangling
  reference that could also occur in production once review-store eviction
  kicks in) — worth knowing if you extend the caching logic further.

See [`CONTRIBUTING.md`](CONTRIBUTING.md#known-gaps-that-are-good-first-contributions)
for how to help close these.

---

## 🤝 Contributing

Contributions are welcome — see [`CONTRIBUTING.md`](CONTRIBUTING.md) for the
local setup, coding standards, and PR checklist.

---

## 🗺 Roadmap Status

Tracked against the 3-phase plan:

**Phase 1 — Downloads (done)**
- [x] Download All ZIP (`/export/batch/zip` — DOCX per article + CSV summary)
- [x] Batch downloads
- [x] Individual downloads (DOCX/PDF per article, single or batch)
- [x] Copy button (single article) + Copy All (batch, markdown-joined)

**Phase 2 — Content depth (done)**
- [x] FAQ generation (already in every response)
- [x] Better SEO report — programmatic 0-100 quality score with specific flags (`app/quality.py`), not just raw metrics
- [x] References/citations — real "Sources Referenced" section auto-appended to every article, built from the actual RAG-matched knowledge-base chunks (`app/llm_providers.py::_append_references`) — not fabricated citations
- [x] Outline preview (`GET /outline`) — deterministic, no LLM call, shows planned sections/word budgets/scope check/grounding before spending a generation

**Phase 3 — Polish (done)**
- [x] True 2500+ word pillar articles — per-section word budgets in prompts; mock mode stays short by design (fixed template), live provider calls follow the budget
- [x] Tone selector — educational / authoritative / patient-friendly / academic / SEO blog, wired into the prompt and cache key
- [x] JSON/Markdown raw export (`POST /export/markdown`, `POST /export/json`) alongside DOCX/PDF
- [x] Better readability metrics — Gunning Fog Index, average sentence length, and a plain-language grade-level label alongside Flesch Reading Ease
- [x] Dashboard (`GET /dashboard`) — generation history, avg quality score, avg word count, cache hit rate, provider breakdown, recent requests
- [x] Persistent storage (SQLite) — review history and dashboard data survive process restarts (`app/db.py`); **on ephemeral-disk hosts (Render free tier), this resets on every spin-down/redeploy same as in-memory did** — real cross-deploy persistence needs a paid plan with a disk, or an external DB
- [x] Internal linking suggestions (`GET /internal-links`) — TF-IDF-ranked related **approved** articles for SEO cluster building
- [x] WordPress/CMS direct publish (`app/cms_wordpress.py`) — optional REST API integration, approved-only, draft-by-default, dry-run mode; **verified via mocked HTTP calls, no live WordPress site was available to test against end-to-end** — run `POST /publish/wordpress/test-connection` against a real site before relying on it

---

## 📤 WordPress Publishing Setup

Optional — the app works fully without it (dry-run mode always works, for
previewing exactly what would be sent).

1. On your WordPress site, go to **Users → Profile → Application Passwords**
   (built into WordPress 5.6+).
2. Enter a name (e.g. "Healthy Gut AI") and click **Add New Application
   Password**. Copy the generated code immediately — it's shown once.
3. Set in `.env`:
   ```env
   WORDPRESS_URL=https://yoursite.com
   WORDPRESS_USERNAME=your-wp-username
   WORDPRESS_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
   ```
4. Verify with `POST /publish/wordpress/test-connection` — read-only, safe
   to call anytime.
5. Only **approved** articles (via the `/review` workflow) can be published;
   drafts and rejected articles return `409`. Posts are created as
   WordPress **drafts** by default — `status=publish` must be explicitly
   requested to go live immediately.

**No WordPress site yet?** Everything above except step 4-5's live network
call is testable via `dry_run=true`, which builds and returns the exact
payload without sending it — this is how the integration was verified
before any real site existed to test against (see `tests/test_wordpress_publish.py`,
which mocks every HTTP call).

---

## 📄 License

Released under the [MIT License](LICENSE).

---

<div align="center">

**If Healthy Gut AI was useful to you, please consider giving it a ⭐ —**
**it genuinely helps the project reach more people.**

[![Star this repo](https://img.shields.io/github/stars/Shweta-Mishra-ai/Healthy-Gut-AI?style=social)](https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI)

</div>
