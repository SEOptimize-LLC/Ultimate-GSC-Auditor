# Ultimate GSC Auditor — Project Guidelines

## Overview

A Streamlit-based Google Search Console auditor that computes 100+ custom SEO metrics, uses AI for query classification and insights, persists data in Supabase, and supports background automation via n8n.

## Architecture

- **Frontend**: Streamlit (multi-page app with `st.Page` + `st.navigation`)
- **Backend**: Python 3.10+
- **Database**: Supabase (PostgreSQL)
- **AI**: OpenRouter API (Gemini 3.1 Flash Lite for classification, Claude Sonnet 4.5 for insights)
- **Automation**: n8n workflows for scheduled data collection
- **APIs**: Google Search Console, Google PageSpeed Insights

## Key Patterns

### Data Shape System
Each unique combination of GSC API dimensions + date range is fetched exactly once and shared across metrics. Defined in `models/data_shapes.py`. The `DataFetcher` analyzes metric dependencies to minimize API calls.

### Metric Computation
Each metric group is a Python class inheriting from `BaseMetricGroup` in `metrics/base_metric.py`. Metrics are registered via `METRIC_REGISTRY` and return `MetricResult` objects.

### URL Filtering
Strong exclusion system removes non-SEO URLs (legal, about, contact, pagination, etc.) before any metric computation. Configuration in `models/url_filter_config.py`.

### AI Pipeline
1. Pre-processing: Branded detection, intent classification, topic clustering (Gemini 3.1 Flash Lite)
2. Metrics computation: All 100 metrics
3. Post-processing: Group narratives (Gemini 3.1 Flash Lite) + Executive summary (Claude Sonnet 4.5)

## File Organization

```
core/         — Infrastructure (OAuth, data fetching, caching, Supabase, URL filtering)
metrics/      — 100 metric computations across 13 modules
ai/           — AI classification and insight generation
models/       — Data models (MetricResult, AuditResult, DataShapes, URLFilterConfig)
reports/      — Report generation (Markdown, HTML, Excel)
utils/        — Helpers (dates, URLs, formatting, benchmarks)
pages/        — Streamlit pages (7 pages)
```

## Conventions

- Metrics are numbered 1-100 and referenced by ID everywhere
- Data shapes are referenced by key (SA_01, SA_02, etc.)
- All dates use ISO format (YYYY-MM-DD)
- GSC data has a 3-day lag (accounted for in `utils/date_utils.py`)
- Site-specific CTR benchmarks only — no industry benchmarks
