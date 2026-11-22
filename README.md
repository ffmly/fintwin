---
title: Fintwin
emoji: ◇
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
license: apache-2.0
short_description: Algerian Digital Market Twin and fintech decision intelligence lab
---

# Fintwin

Fintwin is a **Digital Market Twin** for Algerian founders. It turns an unstructured project brief, product catalog and financial assumptions into decision-ready demand signals, unit economics and scenario stress tests.

## Product surfaces

- Custom full-width FastAPI web app; Gradio is not used in the interface.
- Quick Brief parser: describe the entire business in Darija, Arabic, French or English.
- Optional Guided Builder with clear terminology and skip-friendly assumptions.
- Product catalog through manual entry, pasted rows or CSV import.
- Six curated showcase cases so the portfolio is useful before the first user project.
- Project memory with full configuration, catalog, decision history and searchable behavioral panel.
- Scenario Copilot for pricing, payments, delivery and cost decisions.
- Admin control room for users, runs, model routing, token usage and estimated API cost.
- Official DeepSeek API and Hugging Face Inference Providers API; no local LLM download.

## Current and production databases

Local development currently uses SQLite at `data/fintwin.db`. The current sign-in is a local demo identity field, not secure authentication; project API routes are not protected. `supabase/schema.sql` is a proposed schema only. Supabase Auth, Postgres persistence, and row-level access controls are **not connected yet**. Do not expose real customer or confidential project information through a public deployment of the current build.

## What is live today

- Simulations and persona decisions run with deterministic local rules and synthetic profiles. Scenario comparisons work without an API key for changes understood by the rules parser.
- An LLM is optional for free-form brief extraction, scenario parsing, and narrative explanation. It is not connected until the selected provider has a valid key and model. Without a key, rule-based extraction and simulation continue to work.
- `data/sources.json` lists reference links for future research. The app does not ingest those documents, refresh Algerian prices, or calibrate its coefficients against them. Financial figures are scenario estimates based on founder input and assumptions, not measured market forecasts.
- The 3D/live view is a visual explanation of the same simulated run, not a second data source or a real-time observation of customers.

## Environment

Copy `.env.example` to `.env` and fill secrets locally or in Hugging Face Space Secrets:

```text
ADMIN_PASSWORD=
DEEPSEEK_API_KEY=
HF_TOKEN=
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
```

Only the publishable key may be exposed to browser code. Keep the Supabase secret key server-side.

DeepSeek requests go only to `https://api.deepseek.com/chat/completions`. Hugging Face requests go only to `https://router.huggingface.co/v1/chat/completions`.

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open `http://localhost:7860`.

## Test

```powershell
python -m unittest discover -s tests -v
```

## CSV format

```csv
name,category,price_dzd,cost_dzd,stock,monthly_sales
قميص Oversize,ملابس,3200,1450,25,12
```

## Interpretation

The simulator is a structured hypothesis and decision-support system. It does not guarantee commercial outcomes. Important decisions should be validated with a small real-world market test.
