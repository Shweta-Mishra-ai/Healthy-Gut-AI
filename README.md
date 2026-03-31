# 🥗 Healthy Gut AI

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=for-the-badge&logo=openai&logoColor=white)
![Railway](https://img.shields.io/badge/Deployed-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)
![Status](https://img.shields.io/badge/Status-Live-brightgreen?style=for-the-badge)

**AI-powered medical content generation system — producing SEO-optimised, medically accurate gut health articles instantly.**

[Live Demo](#) · [Report Bug](../../issues) · [Request Feature](../../issues)

</div>

---

## 🧠 What It Does

Healthy Gut AI is a **FastAPI web application** that generates professional, geo-targeted gut health articles using:

- **RAG (Retrieval-Augmented Generation)** — grounded medical knowledge base prevents hallucinations
- **Dual-prompt pipeline** — Prompt 1 writes the article, Prompt 2 optimises it for SEO + geo-targeting
- **Built-in quality metrics** — Flesch Readability Score + Keyword Density calculated on every output
- **Mock mode** — works without an API key for demo/portfolio purposes

---

## 🏗️ Architecture

```
User Input (Topic + Keyword + Geo + Type)
         │
         ▼
   FastAPI Backend
         │
         ├─► RAG Context Lookup (in-memory knowledge base)
         │
         ├─► LLM Pipeline
         │     ├─ Prompt 1 → Medical SEO Article (GPT-4o)
         │     └─ Prompt 2 → Geo-Optimisation + JSON output (GPT-4o)
         │
         └─► Quality Metrics
               ├─ Flesch Reading Ease Score
               └─ Keyword Density %
                        │
                        ▼
              Rendered Output (Markdown → HTML)
              Meta Description · URL Slug · FAQs · CTAs · Schema JSON-LD
```

---

## 🚀 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, FastAPI, Uvicorn |
| AI | OpenAI GPT-4o (with mock fallback) |
| RAG | In-memory knowledge base (Pydantic models) |
| Frontend | Vanilla JS, Marked.js, CSS Glass UI |
| Deployment | Railway (Procfile + ENV vars) |
| Serverless | Mangum (AWS Lambda / Vercel compatible) |

---

## 📁 Project Structure

```
Healthy-Gut-AI/
│
├── main.py                    # FastAPI app — routes, LLM logic, metrics
├── Procfile                   # Railway deployment config
├── requirements.txt           # Python dependencies
│
├── api/
│   └── index.py               # Mangum serverless wrapper (Vercel/Lambda)
│
├── static/
│   ├── index.html             # Frontend UI
│   ├── style.css              # Glass morphism design
│   └── app.js                 # Form submit + results render logic
│
├── prompts/
│   ├── prompt1_medical_seo_article.txt     # Medical article generation prompt
│   └── prompt2_geo_ai_optimization.txt     # Geo-SEO optimisation prompt
│
└── samples/
    ├── article1_pillar.md     # Sample pillar article output
    └── article2_supporting.md # Sample supporting article output
```

---

## ⚙️ Local Setup

### 1. Clone & Install

```bash
git clone https://github.com/Shweta-Mishra-ai/Healthy-Gut-AI.git
cd Healthy-Gut-AI
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file (optional — app runs in mock mode without it):

```env
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run

```bash
uvicorn main:app --reload --port 8000
```

Open → `http://localhost:8000`

---

## 🌐 Deploy on Railway

### Step 1 — Connect Repo
Push to GitHub → Railway Dashboard → **New Project** → **Deploy from GitHub repo**

### Step 2 — Set Environment Variables
Railway Dashboard → Your Service → **Variables** tab:

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | `sk-your-openai-key` |

> **Note:** If `OPENAI_API_KEY` is not set, the app runs in **mock mode** (returns template articles). This is fine for demo/portfolio.

### Step 3 — Deploy
Railway auto-detects the `Procfile` and deploys. No extra config needed.

```
web: uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
```

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Frontend UI |
| `POST` | `/generate` | Generate article (form data) |
| `GET` | `/health` | Health check |
| `GET` | `/debug` | List all routes |

### POST `/generate` — Request Body (form-data)

| Field | Type | Example |
|---|---|---|
| `topic` | string | `Irritable Bowel Syndrome` |
| `primary_keyword` | string | `IBS symptoms` |
| `geo_target` | string | `New York, USA` |
| `article_type` | `pillar` / `supporting` | `pillar` |

### Response

```json
{
  "optimized_article_markdown": "# IBS Guide...",
  "meta_description": "Learn about IBS symptoms...",
  "url_slug": "irritable-bowel-syndrome-guide",
  "faqs": [...],
  "schema_json_ld": {...},
  "cta_soft": "Explore more resources...",
  "cta_direct": "Try Healthy Gut AI FREE...",
  "metrics": {
    "readability": { "fleschReadingEase": 62.4 },
    "keywordDensity": { "keywordDensityPercent": 1.8 }
  }
}
```

---

## 🧪 Features

- ✅ **Mock mode** — works without OpenAI key (portfolio-safe)
- ✅ **RAG grounding** — IBS, IBD, Gut Microbiome knowledge base
- ✅ **Geo-targeting** — location-aware content optimisation
- ✅ **Dual article types** — Pillar (2500+ words) / Supporting (1000+ words)
- ✅ **SEO metrics** — Keyword Density + Flesch Readability Score
- ✅ **Schema JSON-LD** — structured data for Google rich snippets
- ✅ **Print/PDF export** — one-click via browser print dialog
- ✅ **Serverless ready** — Mangum wrapper for AWS Lambda / Vercel

---

## 🗺️ Roadmap

- [ ] Expand RAG knowledge base (GERD, Crohn's, Celiac)
- [ ] Add Groq Llama 3.3 70B as free-tier LLM fallback
- [ ] Bulk article generation (CSV input)
- [ ] Export to DOCX / PDF
- [ ] Article history with local storage

---

## 👩‍💻 Author

**Shweta Mishra** — AI/ML Engineer & Open Source Builder

[![GitHub](https://img.shields.io/badge/GitHub-Shweta--Mishra--ai-181717?style=flat&logo=github)](https://github.com/Shweta-Mishra-ai)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=flat&logo=linkedin)](https://linkedin.com/in/shweta-mishra)

---

*Built with FastAPI + OpenAI GPT-4o. Deployed on Railway.*
