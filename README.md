🎯 Healthy-Gut-AI
AI-Powered Medical Content Generation System

This repository contains my solution for Problem.
It demonstrates my ability to work with:

🔹 LLM prompt engineering

🔹 n8n workflows

🔹 SEO optimization

🔹 Readability + keyword metrics

🔹 GitHub version-control

🔹 Modular and scalable AI pipelines

🧠 Project Purpose

Healthy-Gut-AI automatically generates medically accurate, SEO-optimized, and readability-checked articles on gut health topics using:

✨ LLM Prompts

✨ JS Metrics Scripts

✨ n8n Automation

✨ Google Sheets Inputs

This showcases real workflow automation + AI engineering skills.

💻 **Quick Start (Standalone):**

Run the example script to see metrics in action:

```bash
node example_standalone.js
```

Or use the metrics scripts directly:

```bash
# Keyword density
node metrics/keyword_density.js "<article text>" "<keyword>"

# Readability check  
node metrics/readability_check.js "<article text>"
```

📁 Repository Structure
Healthy-Gut-AI/
│
├── prompts/
│   ├── prompt1_medical_seo_article.txt
│   └── prompt2_geo_ai_optimization.txt
│
├── metrics/
│   ├── keyword_density.js
│   └── readability_check.js
│
├── example_standalone.js
│
├── samples/
│   ├── article1_pillar.md
│   └── article2_supporting.md
│
└── README.md


Each folder has a specific purpose to keep the workflow modular and scalable.

✍️ Prompt Details
🔹 Prompt 1 — Medical SEO Article Generator

Designed to create:

Medically accurate articles

Pillar (2500–3000 words) or Supporting (1000–1500 words)

Structured headings

Comparison tables

Diet recommendations

Keyword optimization

Medical disclaimers

🔹 Prompt 2 — Geo-Optimized SEO Enhancer

Adds:

Location-based optimization

Meta description

URL slug

FAQs

Schema (JSON-LD)

Featured snippet improvements

CTAs

🧮 Metrics Scripts
📌 keyword_density.js

Calculates:

Total words

Keyword count

Keyword density (%)

Ensures SEO quality.

✅ **Supports both n8n workflows and standalone Node.js execution**

**Usage:**
- **n8n:** Automatically uses `$json.optimized_article_markdown` and `$json.primary_keyword`
- **Standalone:** `node metrics/keyword_density.js "<article>" "<keyword>"`

📌 readability_check.js

Calculates:

Flesch Reading Ease score

Sentence complexity

Syllables per word

Ensures the article is readable for a general audience.

✅ **Supports both n8n workflows and standalone Node.js execution**

**Usage:**
- **n8n:** Automatically uses `$json.optimized_article_markdown`
- **Standalone:** `node metrics/readability_check.js "<article>"`

⚙️ Workflow Overview (n8n)
1️⃣ Google Sheet Input

topic

primary_keyword

geo_target

article_type

2️⃣ Workflow 1

➡ Outline generator

3️⃣ Workflow 2

➡ Draft generation using Prompt 1

4️⃣ Workflow 3

➡ Optimization using Prompt 2
➡ Keyword density + readability checks (metrics scripts)

5️⃣ Save outputs inside /samples/
📝 Sample Outputs

✔ article1_pillar.md — Pillar article sample
✔ article2_supporting.md — Supporting article sample

These demonstrate how the pipeline generates structured, human-readable content.

🧩 Architecture Diagram (Text Version)
Google Sheet → n8n Workflow 1 (Outline)
            → n8n Workflow 2 (Prompt 1 → Draft)
            → n8n Workflow 3 (Prompt 2 → Optimization)
            → Metrics JS (Density + Readability)
            → Final Output (samples/)

🎥 Demo Video Guidelines

Your demo video should show:

GitHub repository

prompts folder

metrics folder

samples outputs

n8n workflows

Running the workflow

Article generation

Explanation of logic

Summary

🚀 Conclusion

This project fully satisfies Problem 1 of the assignment by showing strong skills in:

AI automation

Workflow engineering

Prompt design

SEO-focused content generation

GitHub versioning

JS scripting

This repository is a clean, professional example of an AI-powered content generation pipeline.

🙌 Thank You

If you’d like to explore the workflow or ask questions, feel free!
# 🥗 Healthy-Gut-AI: Medical Content Generation System

![Status](https://img.shields.io/badge/Status-Active-success?style=for-the-badge)
![n8n](https://img.shields.io/badge/n8n-Workflow_Automation-FF6D5A?style=for-the-badge&logo=n8n&logoColor=white)
![AI](https://img.shields.io/badge/GenAI-LLM_Engineering-blue?style=for-the-badge)

> **✅ Latest Update:** Metrics scripts (`keyword_density.js` and `readability_check.js`) now support both n8n workflows and standalone Node.js execution. Fixed ReferenceError when running scripts outside n8n context.

### 🏥 Project Overview
**Healthy-Gut-AI** is an automated pipeline designed to generate medically accurate, SEO-optimized, and readability-checked content. It solves the problem of creating high-quality medical articles at scale by combining **Large Language Models (LLMs)** with **Rigorous Verification Metrics**.

### 🚀 Key Features
* **🤖 LLM Prompt Engineering:** Advanced prompts designed to hallucination-proof medical advice.
* **⚙️ n8n Automation:** End-to-end workflow management from topic selection to draft generation.
* **🔍 SEO Optimization:** Auto-insertion of keywords, meta-tags, and Schema markup.
* **📊 Quality Metrics:** Custom scripts to calculate Readability Scores and Keyword Density before publishing.

### 📂 Repository Structure
This project is modular to ensure scalability:
* `prompts/` - Contains engineered prompts for Medical Accuracy & Geo-Targeting.
* `metrics/` - JavaScript tools for `keyword_density.js` and `readability_check.js`. Works in both n8n and standalone modes.
* `samples/` - Example output articles (Pillar Content & Supporting Blogs).
* `workflows/` - (Currently Updating) n8n JSON workflow files.

### 🧠 Logic & Engineering
#### 1. Medical SEO Generator (Prompt 1)
Designed to create strict "Pillar Content" (2500+ words) that includes:
* Comparison Tables & Diet Plans.
* Medical Disclaimers & Citations.
* Structured H1, H2, H3 hierarchy.

#### 2. Geo-Optimization Engine (Prompt 2)
Enhances content for local search intent:
* Adds Location-based keywords.
* Generates FAQ Schema (JSON-LD).
* Optimizes Meta Descriptions for higher CTR.

### 🛠 Tech Stack
* **Core:** JavaScript, n8n (Workflow Automation)
* **AI Models:** GPT-4 / Claude (via API)
* **Data:** Google Sheets (Input Source)
* **Version Control:** Git & GitHub

---
*Developed by Shweta Mishra | Focusing on AI Agentic Workflows.*

