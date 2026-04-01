---
Title: Healthy Gut AI
emoji: 🥗
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: AI-powered medical SEO article generator for gut health
---

# Healthy Gut AI

> Dual-prompt RAG pipeline for generating geo-targeted, SEO-optimised medical content — with built-in readability and keyword density metrics.

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://shwetam242-healthy-gut-ai.hf.space)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/fastapi-0.100+-teal)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow)](LICENSE)
[![HF Spaces](https://img.shields.io/badge/deployed-HF%20Spaces-orange)](https://huggingface.co/spaces/Shwetam242/Healthy-Gut-AI)

---

## Overview

Healthy Gut AI started as an n8n automation workflow (V1) — Google Sheets input, chained LLM prompts, standalone JS metric scripts. It worked, but the architecture was brittle: no web interface, metrics ran in isolation, and deployment was manual.

V2 replaces the entire pipeline with a FastAPI backend. The JS metric scripts are ported to Python and integrated directly into the API response. A RAG layer grounds every generation in a verified medical knowledge base, preventing hallucination on clinical claims.

---

## Architecture

```
                        ┌─────────────────────┐
                        │     Web Browser      │
                        │  topic · keyword     │
                        │  geo · article_type  │
                        └──────────┬──────────┘
                                   │ POST /generate
                                   ▼
┌──────────────────────────────────────────────────────┐
│                    FastAPI Backend                   │
│                                                      │
│  ┌─────────────────┐        ┌─────────────────────┐  │
│  │   RAG Engine    │──ctx──►│    LLM Pipeline     │  │
│  │                 │        │                     │  │
│  │  gut microbiome │        │  prompt_1           │  │
│  │  IBS / IBD      │        │  └─► medical draft  │  │
│  │  FODMAP diet    │        │       (GPT-4o)      │  │
│  └─────────────────┘        │                     │  │
│                             │  prompt_2           │  │
│  ┌─────────────────┐        │  └─► SEO + geo opt  │  │
│  │  Metrics Engine │◄───────│       (GPT-4o JSON) │  │
│  │                 │        └─────────────────────┘  │
│  │  flesch score   │                                  │
│  │  keyword density│                                  │
│  └────────┬────────┘                                  │
└───────────┼──────────────────────────────────────────┘
            │
            ▼
  article · metrics · meta · slug · faqs · schema · cta
```

---

## Stack

| Layer | Choice | Reason |
|---|---|---|
| API | FastAPI + Uvicorn | Async, typed, auto-docs |
| AI | OpenAI GPT-4o | JSON mode for structured output |
| RAG | In-memory dict | No vector DB overhead for small KB |
| Metrics | Custom Python | Flesch Reading Ease, KW density |
| Frontend | Vanilla JS + Marked.js | Zero build tooling |
| Deploy | HF Spaces (Docker) | Free, persistent, public URL |
| CI/CD | GitHub Actions | Push-to-deploy on `main` |

---

## Versions

### V1 — n8n Automation
- **Input:** Google Sheets
- **Pipeline:** n8n nodes → LLM prompts → JS metric scripts
- **Output:** Markdown files in `/samples`
- **Problem:** Brittle workflows, no UI, hard to share, metrics isolated from pipeline

### V2 — FastAPI App (current)
- **Input:** Web form
- **Pipeline:** FastAPI → RAG → dual GPT-4o prompts → integrated metrics
- **Output:** JSON response rendered in browser
- **Deployed:** Hugging Face Spaces via GitHub Actions

---

## Quickstart

```bash
git clone https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI
cd Healthy-Gut-AI
pip install -r requirements.txt
uvicorn main:app --reload --port 7860
```

App runs in **mock mode** without `OPENAI_API_KEY` — returns structured template articles with real metric calculations. Useful for UI development and demos.

```bash
export OPENAI_API_KEY=sk-...   # optional
```

---

## API

```
POST /generate
```

```json
{
  "topic": "Irritable Bowel Syndrome",
  "primary_keyword": "IBS symptoms",
  "geo_target": "London, UK",
  "article_type": "pillar"
}
```

Response:

```json
{
  "optimized_article_markdown": "...",
  "meta_description": "...",
  "url_slug": "ibs-symptoms-guide",
  "faqs": [...],
  "schema_json_ld": { "@type": "Article", ... },
  "cta_soft": "...",
  "cta_direct": "...",
  "metrics": {
    "readability": { "fleschReadingEase": 62.4 },
    "keywordDensity": { "keywordDensityPercent": 1.8 }
  }
}
```

```
GET /health   →  { "status": "ok" }
```

---

## Deployment

Auto-deploys to Hugging Face Spaces on every push to `main` via `.github/workflows/hf-sync.yml`.

Manual deploy:

```bash
git remote add hf https://huggingface.co/spaces/Shwetam242/Healthy-Gut-AI
git push hf main --force
```

Required secrets:

| Secret | Where |
|---|---|
| `OPENAI_API_KEY` | HF Space → Settings → Secrets |
| `HF_TOKEN` | GitHub repo → Settings → Actions secrets |

---

## Project Structure

```
.
├── main.py                        # app, routes, RAG, LLM, metrics
├── Dockerfile
├── requirements.txt
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── prompts/
│   ├── prompt1_medical_seo_article.txt
│   └── prompt2_geo_ai_optimization.txt
├── samples/
│   ├── article1_pillar.md
│   └── article2_supporting.md
└── .github/
    └── workflows/
        └── hf-sync.yml
```

---

## Roadmap

- [ ] Groq Llama 3.3 70B fallback for zero-cost inference
- [ ] Expand RAG — GERD, Crohn's, Celiac, SIBO
- [ ] Batch generation via CSV upload
- [ ] DOCX / PDF export
- [ ] Persistent article history

---

## License

[MIT](LICENSE)

---

*If this project was useful, a ⭐ is appreciated.*
