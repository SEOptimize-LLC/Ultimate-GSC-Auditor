# n8n Automation Workflows

## Overview

Two automated workflows for background data collection:

1. **Daily Data Collection** — Fetches yesterday's GSC data for all active properties
2. **Weekly URL Inspection** — Batch inspects URLs for indexation status

## Setup

### Prerequisites

- n8n instance (self-hosted or cloud)
- Supabase project with tables created
- Google OAuth refresh tokens stored in Supabase

### Environment Variables (n8n credentials)

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-client-secret
OPENROUTER_API_KEY=your-openrouter-key
```

## Workflow 1: Daily Data Collection

**Schedule:** Daily at 6:00 AM UTC

**Steps:**
1. Query Supabase for active properties with stored refresh tokens
2. For each property:
   - Exchange refresh token for access token
   - Fetch yesterday's GSC data for all shape dimensions
   - Upsert rows into `gsc_raw_data` table
   - Detect new queries not in `ai_classifications`
   - Classify new queries via OpenRouter (Gemini Flash Lite)
   - Store classifications in `ai_classifications`

**Import:** Use `daily-data-collection.json` in n8n

## Workflow 2: Weekly URL Inspection

**Schedule:** Sundays at 4:00 AM UTC

**Steps:**
1. Query Supabase for active properties
2. For each property:
   - Get top URLs by impressions (max 2,000)
   - Call GSC URL Inspection API for each URL
   - Store results in `url_inspection_results`

**Import:** Use `weekly-url-inspection.json` in n8n

## Supabase Schema

Both workflows expect these tables to exist:
- `properties` (property_url, refresh_token, ...)
- `gsc_raw_data` (property_url, shape_name, data, ...)
- `ai_classifications` (property_url, query, is_branded, intent, topic_cluster)
- `url_inspection_results` (property_url, url, inspection_result)
