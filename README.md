---
title: Healthy Gut AI
emoji: 🥗
colorFrom: indigo
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: AI-powered medical SEO article generator for gut health
---

<div align="center">

<img src="https://img.shields.io/badge/version-2.0-blue?style=for-the-badge" />
<img src="https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
<img src="https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white" />
<img src="https://img.shields.io/badge/Deployed-HuggingFace_Spaces-FFD21E?style=for-the-badge&logo=huggingface&logoColor=black" />
<img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />

# 🥗 Healthy Gut AI

**Production-grade AI content engine for medically accurate, SEO-optimised gut health articles.**

[🚀 Live Demo](https://shwetam242-healthy-gut-ai.hf.space) · [🐛 Issues](../../issues) · [⭐ Star this repo](../../stargazers)

> **If this project helped you or impressed you — a ⭐ star means a lot and keeps this project alive!**

</div>

---

## 🧭 Project Journey

This project has gone through two major versions — each solving real engineering problems.

### V1 — n8n Automation Pipeline
The original version was built as an **n8n workflow automation**:
- Google Sheets as input source
- LLM prompts chained via n8n nodes
- JavaScript scripts for keyword density and readability scoring
- Output saved to `/samples/` folder

**Limitations hit:** Workflows were brittle, no public UI, JS metrics ran in isolation, and the whole system was hard to deploy and share.

### V2 — Production FastAPI Web App ← *current*
A complete re-engineering from the ground up:

| What changed | V1 | V2 |
|---|---|---|
| Runtime | n8n nodes | FastAPI backend |
| Metrics | Standalone JS scripts | Python, integrated into API |
| Knowledge | Raw prompts | RAG knowledge base |
| UI | None | Glass morphism web app |
| Deployment | Local / n8n cloud | Hugging Face Spaces (Docker) |
| Sync | Manual | GitHub Actions → HF auto-deploy |

> This isn't just a rewrite. It's an architectural decision — knowing **when to refactor** is as important as knowing how to build.

---

## ✨ What It Does

Takes four inputs, returns a fully production-ready medical article in seconds:

```
Topic          →  "Irritable Bowel Syndrome"
Keyword        →  "IBS symptoms and treatment"
Geo-Target     →  "Mumbai, India"
Article Type   →  Pillar (2500+ words) | Supporting (1000+ words)
```

**Output:**
- Full Markdown article with H1/H2/H3 hierarchy
- Flesch Readability Score + Keyword Density %
- SEO Meta Description + clean URL Slug
- FAQ section (schema-ready JSON)
- JSON-LD Schema markup (Google rich snippets)
- Geo-targeted Soft CTA + Direct CTA

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│                   USER BROWSER                   │
│        Topic · Keyword · Geo · Article Type      │
└─────────────────────┬────────────────────────────┘
                      │ POST /generate
                      ▼
┌──────────────────────────────────────────────────┐
│               FASTAPI BACKEND                    │
│                                                  │
│  ┌───────────────┐    ┌────────────────────────┐ │
│  │  RAG Engine   │───►│     LLM Pipeline       │ │
│  │               │    │                        │ │
│  │  · Gut Health │    │  Prompt 1              │ │
│  │  · IBS / IBD  │    │  └─ Medical Draft      │ │
│  │  · Microbiome │    │       (GPT-4o)         │ │
│  └───────────────┘    │  Prompt 2              │ │
│                       │  └─ SEO + Geo Optimise │ │
│  ┌───────────────┐    │       (GPT-4o JSON)    │ │
│  │ Metrics Engine│◄───└────────────────────────┘ │
│  │               │                               │
│  │ · Flesch Score│                               │
│  │ · KW Density  │                               │
│  └───────────────┘                               │
└─────────────────────┬────────────────────────────┘
                      │ JSON Response
                      ▼
┌──────────────────────────────────────────────────┐
│  Article · Metrics · Meta · Slug · FAQs · Schema │
└──────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| AI | OpenAI GPT-4o (dual-prompt pipeline) |
| RAG | In-memory medical knowledge base |
| Metrics | Custom Python (Flesch + KW Density) |
| Frontend | Vanilla JS, Marked.js, CSS Glass UI |
| Deployment | Hugging Face Spaces (Docker) |
| CI/CD | GitHub Actions → HF auto-sync |

---

## 📁 Structure

```
Healthy-Gut-AI/
├── main.py                          # FastAPI app, RAG, LLM, metrics
├── Dockerfile                       # HF Spaces Docker config
├── requirements.txt                 # Dependencies
├── static/
│   ├── index.html                   # Web UI
│   ├── style.css                    # Glass morphism design
│   └── app.js                       # Form logic + results render
├── prompts/
│   ├── prompt1_medical_seo_article.txt
│   └── prompt2_geo_ai_optimization.txt
├── samples/
│   ├── article1_pillar.md
│   └── article2_supporting.md
└── .github/workflows/
    └── hf-sync.yml                  # Auto-deploy to HF on push
```

---

## ⚙️ Local Setup

```bash
git clone https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI.git
cd Healthy-Gut-AI
pip install -r requirements.txt

# Optional — without this, mock mode runs
export OPENAI_API_KEY=sk-your-key

uvicorn main:app --reload --port 7860
# Open: http://localhost:7860
```

> **No API key?** App runs in **mock mode** — returns structured template articles with real metrics. Safe for demos.

---

## 🌐 Deploy (Hugging Face Spaces)

```bash
# Auto-deploys via GitHub Actions on every push to main
# Manual trigger: edit any file → commit → push
```

Or set up from scratch:
1. New Space → SDK: `Docker` → Port: `7860`
2. Link GitHub repo
3. Add secret: `OPENAI_API_KEY`
4. Done — builds automatically

---

## 🔌 API

### `POST /generate`

```bash
curl -X POST https://shwetam242-healthy-gut-ai.hf.space/generate \
  -F "topic=IBS" \
  -F "primary_keyword=IBS symptoms" \
  -F "geo_target=London, UK" \
  -F "article_type=pillar"
```

**Response shape:**
```json
{
  "optimized_article_markdown": "...",
  "meta_description": "...",
  "url_slug": "ibs-guide",
  "faqs": [...],
  "schema_json_ld": {...},
  "cta_soft": "...",
  "cta_direct": "...",
  "metrics": {
    "readability": { "fleschReadingEase": 62.4 },
    "keywordDensity": { "keywordDensityPercent": 1.8 }
  }
}
```

### `GET /health` → `{"status": "ok"}`

---

## 🗺️ Roadmap

- [ ] Groq Llama 3.3 70B as free-tier LLM fallback
- [ ] Expand RAG — GERD, Crohn's, Celiac Disease
- [ ] Bulk generation via CSV upload
- [ ] DOCX / PDF export
- [ ] Article history

---

## 📜 License

MIT — free to use, modify, and distribute with attribution. See [LICENSE](LICENSE).

---

<div align="center">

**⭐ Found this useful? Star it — it genuinely helps! ⭐**

*FastAPI · OpenAI GPT-4o · Hugging Face Spaces · GitHub Actions*

</div>
