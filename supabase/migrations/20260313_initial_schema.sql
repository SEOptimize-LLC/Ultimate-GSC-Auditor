-- Ultimate GSC Auditor — Initial Database Schema
-- Run this migration to create all required tables.

-- 1. Properties table
CREATE TABLE IF NOT EXISTS properties (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    property_url TEXT UNIQUE NOT NULL,
    display_name TEXT DEFAULT '',
    refresh_token TEXT,  -- Encrypted OAuth refresh token for n8n
    background_collection_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_properties_url ON properties(property_url);

-- 2. Audit runs table
CREATE TABLE IF NOT EXISTS audit_runs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    property_url TEXT NOT NULL REFERENCES properties(property_url),
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    health_score INTEGER NOT NULL DEFAULT 0,
    health_grade TEXT NOT NULL DEFAULT 'F',
    total_findings INTEGER NOT NULL DEFAULT 0,
    severity_counts JSONB DEFAULT '{}',
    metrics_executed INTEGER[] DEFAULT '{}',
    ai_executive_summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_runs_property ON audit_runs(property_url);
CREATE INDEX idx_audit_runs_created ON audit_runs(created_at DESC);

-- 3. Metric results table
CREATE TABLE IF NOT EXISTS metric_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    audit_run_id UUID NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    metric_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    computed_value DOUBLE PRECISION,
    affected_count INTEGER DEFAULT 0,
    recommendations TEXT[] DEFAULT '{}',
    trend_direction TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_metric_results_run ON metric_results(audit_run_id);
CREATE INDEX idx_metric_results_metric ON metric_results(metric_id);

-- 4. AI group analyses table
CREATE TABLE IF NOT EXISTS ai_group_analyses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    audit_run_id UUID NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    narrative TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_group_run ON ai_group_analyses(audit_run_id);

-- 5. Raw GSC data archive
CREATE TABLE IF NOT EXISTS gsc_raw_data (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    property_url TEXT NOT NULL,
    shape_name TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_gsc_raw_property_shape
    ON gsc_raw_data(property_url, shape_name);
CREATE INDEX idx_gsc_raw_created
    ON gsc_raw_data(created_at DESC);

-- 6. AI classification cache
CREATE TABLE IF NOT EXISTS ai_classifications (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    property_url TEXT NOT NULL,
    query TEXT NOT NULL,
    is_branded BOOLEAN DEFAULT FALSE,
    intent TEXT DEFAULT 'informational',
    topic_cluster TEXT DEFAULT 'uncategorized',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(property_url, query)
);

CREATE INDEX idx_ai_class_property
    ON ai_classifications(property_url);

-- 7. URL inspection results cache
CREATE TABLE IF NOT EXISTS url_inspection_results (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    property_url TEXT NOT NULL,
    url TEXT NOT NULL,
    inspection_result JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(property_url, url)
);

CREATE INDEX idx_url_insp_property
    ON url_inspection_results(property_url);

-- Enable Row Level Security (RLS)
ALTER TABLE properties ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE metric_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_group_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE gsc_raw_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_classifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE url_inspection_results ENABLE ROW LEVEL SECURITY;

-- RLS policies (allow all for authenticated users via anon key)
-- In production, scope by user ID
CREATE POLICY "Allow all for anon" ON properties
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON audit_runs
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON metric_results
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON ai_group_analyses
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON gsc_raw_data
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON ai_classifications
    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all for anon" ON url_inspection_results
    FOR ALL USING (true) WITH CHECK (true);
