# Ultimate GSC Auditor

A production-grade Streamlit application that connects to Google Search Console via OAuth, computes **100 custom SEO metrics** across 13 categories, uses AI for query classification and insight generation, and persists data in Supabase for historical tracking.

## Features

- **100 SEO Metrics** organized into 13 categories:
  - Query Performance (1-12)
  - Click & CTR Analysis (13-21)
  - Impression & Visibility (22-27)
  - Position & Ranking (28-34)
  - Crawl & Index Health (35-44)
  - Content Health (45-48)
  - Device & Segment (49-50)
  - Query Intent & Topical (51-60)
  - Click Behavior (61-68)
  - Impression Quality (69-77)
  - Ranking Velocity (78-84)
  - Indexation & Coverage (85-94)
  - Content Portfolio (95-100)

- **Smart Data Fetching** — 23 unique API query shapes, each fetched exactly once regardless of how many metrics need it
- **AI-Powered Classification** — Branded query detection, search intent classification, topic clustering (Gemini Flash Lite via OpenRouter)
- **AI Insights** — Executive summary, group narratives, content optimization plan (Claude Sonnet via OpenRouter)
- **URL Filtering** — 44 default exclusion rules to focus on SEO-relevant pages
- **Historical Tracking** — Supabase persistence survives GSC's 16-month data limit
- **Reports** — Export as Markdown, HTML, or Excel
- **Background Automation** — n8n workflows for daily data collection and weekly URL inspection

## Architecture

```text
Streamlit Cloud (7-page app)
    |
    +---> Google Search Console API (OAuth 2.0)
    |     - Search Analytics, URL Inspection, Sitemaps
    |
    +---> Supabase (PostgreSQL)
    |     - Audit history, raw GSC data archive
    |     - AI classification cache, URL inspections
    |
    +---> OpenRouter API
    |     - Gemini Flash Lite: classification (pre-processing)
    |     - Claude Sonnet: insights (post-processing)
    |
    +---> n8n (optional background automation)
          - Daily GSC data collection
          - Weekly URL inspections
```

## Setup

### 1. Clone and deploy

```bash
git clone https://github.com/SEOptimize-LLC/Ultimate-GSC-Auditor.git
```

Deploy to [Streamlit Cloud](https://streamlit.io/cloud) by connecting your GitHub repo.

### 2. Configure secrets (Streamlit Cloud)

All credentials are stored in the **Streamlit Cloud Secrets** tab — no local files or environment variables needed.

1. Go to your app on [Streamlit Cloud](https://share.streamlit.io)
2. Click **Settings** (gear icon) > **Secrets**
3. Paste the following (fill in your values):

```toml
# Required — Google OAuth
GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "your-client-secret"
GOOGLE_REDIRECT_URI = "https://your-app.streamlit.app"

# Optional — AI classification and insights
OPENROUTER_API_KEY = "sk-or-v1-your-key"

# Optional — Historical data persistence
SUPABASE_URL = "https://your-project.supabase.co"
SUPABASE_ANON_KEY = "your-anon-key"
```

See [secrets_template.toml](secrets_template.toml) for the full template.

### 3. Google OAuth setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the **Google Search Console API**
3. Create OAuth 2.0 credentials (Web application type)
4. Add your Streamlit Cloud URL (e.g., `https://your-app.streamlit.app`) as an authorized redirect URI
5. Copy the client ID and secret into the Streamlit Cloud Secrets tab

### 4. Local development (optional)

If running locally instead of Streamlit Cloud:

```bash
pip install -r requirements.txt
cp secrets_template.toml .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your credentials
streamlit run app.py
```

### 5. Supabase (optional)

If you want historical tracking, run the migration:

```sql
-- Apply supabase/migrations/20260313_initial_schema.sql
-- Creates 7 tables: properties, audit_runs, metric_results,
-- ai_group_analyses, gsc_raw_data, ai_classifications,
-- url_inspection_results
```

## Pages

| Page | Purpose |
| ---- | ------- |
| **Connect** | Google OAuth sign-in, property selection, brand name |
| **Configure** | Date range, URL filters, metric scope, run audit |
| **Dashboard** | Health score (A-F), severity distribution, top findings |
| **Metrics Explorer** | Deep-dive into any of the 100 metrics |
| **AI Insights** | Executive summary, content plan, category narratives |
| **Historical** | Audit trend charts, run-to-run comparison |
| **Export** | Download Markdown, HTML, Excel reports |

## Project Structure

```text
├── app.py                    # Entry point
├── pages/                    # 7 Streamlit pages
├── core/                     # GSC client, data fetcher, Supabase, URL filter
├── metrics/                  # 100 metrics in 13 modules
├── ai/                       # OpenRouter client, classifiers, insight generator
├── models/                   # Data models (MetricResult, AuditResult, DataShapes)
├── reports/                  # Markdown, HTML, Excel export
├── utils/                    # Date, URL, formatting helpers
├── supabase/migrations/      # Database schema
└── n8n/                      # Automation workflows
```

## AI Cost Estimates

| Scenario | Classification | Insights | Total |
| -------- | -------------- | -------- | ----- |
| 2,000 queries | ~$0.11 | ~$0.75 | ~$0.90 |
| 10,000 queries | ~$0.55 | ~$0.75 | ~$1.30 |
| 50,000 queries | ~$2.76 | ~$0.75 | ~$3.50 |
| Repeat audit (cached) | ~$0.05-0.50 | ~$0.75 | ~$1.00-1.25 |

## License

Private repository. All rights reserved.
