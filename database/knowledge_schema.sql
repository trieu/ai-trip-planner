-- ============================================================
-- LEO Data Activation & Alert Center – Unified Database Schema
-- Database: PostgreSQL 16+
-- Architecture: Multi-tenant, Event-Driven, Hybrid (SQL + Vector + Graph)
-- ============================================================

-- =========================
-- 1. REQUIRED EXTENSIONS & GRAPH INIT
-- =========================
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid() and hashing (SHA256)
CREATE EXTENSION IF NOT EXISTS vector;    -- High-dimensional vector storage
CREATE EXTENSION IF NOT EXISTS citext;    -- Case-Insensitive Text
CREATE EXTENSION IF NOT EXISTS age;       -- Apache AGE for Graph Database
CREATE EXTENSION IF NOT EXISTS postgis;   -- Spatial data support

-- Load AGE functionality and set path
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Initialize the master graph for LEO CDP
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_graph WHERE name = 'leo_cdp_graph') THEN
        PERFORM ag_catalog.create_graph('leo_cdp_graph');
    END IF;
END
$$;

-- =========================
-- 2. SHARED UTILITIES
-- =========================
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================
-- 3. TENANT (CORE NAMESPACE)
-- =========================
CREATE TABLE IF NOT EXISTS tenant (
    tenant_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active', 
    keycloak_realm      TEXT NOT NULL,        
    keycloak_client_id  TEXT NOT NULL,        
    keycloak_org_id     TEXT,                 
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tenant_keycloak_realm UNIQUE (keycloak_realm, tenant_name)
);

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_select_policy ON tenant FOR SELECT
USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

CREATE POLICY tenant_insert_policy ON tenant FOR INSERT WITH CHECK (true);
CREATE POLICY tenant_update_policy ON tenant FOR UPDATE WITH CHECK (true);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_tenant_updated_at' AND tgrelid = 'tenant'::regclass) THEN
        CREATE TRIGGER trg_tenant_updated_at BEFORE UPDATE ON tenant
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ============================================================
-- 4. CDP PROFILES (The "User" Entity)
-- ============================================================
CREATE TABLE IF NOT EXISTS cdp_profiles (
    tenant_id UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id TEXT PRIMARY KEY,
    
    identities JSONB NOT NULL DEFAULT '[]'::jsonb,
    primary_email CITEXT,
    secondary_emails JSONB NOT NULL DEFAULT '[]'::jsonb,
    primary_phone TEXT,
    secondary_phones JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    first_name TEXT,
    last_name TEXT,
    living_location TEXT,
    living_country TEXT,
    living_city TEXT,
    
    job_titles JSONB NOT NULL DEFAULT '[]'::jsonb,
    data_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    content_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    media_channels JSONB NOT NULL DEFAULT '[]'::jsonb,
    behavioral_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    segments JSONB NOT NULL DEFAULT '[]'::jsonb,
    journey_maps JSONB NOT NULL DEFAULT '[]'::jsonb,
    segment_snapshots JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    event_statistics JSONB NOT NULL DEFAULT '{}'::jsonb,
    top_engaged_touchpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    
    interest_embedding vector(1536),
    
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ext_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'active',
    
    CONSTRAINT uq_cdp_profile_identity UNIQUE (tenant_id, profile_id)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_cdp_profiles_updated_at' AND tgrelid = 'cdp_profiles'::regclass) THEN
        CREATE TRIGGER trg_cdp_profiles_updated_at BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

CREATE OR REPLACE FUNCTION prevent_snapshot_removal()
RETURNS TRIGGER AS $$
BEGIN
    IF jsonb_array_length(NEW.segment_snapshots) < jsonb_array_length(OLD.segment_snapshots) THEN
        RAISE EXCEPTION 'Data Integrity Violation: segment_snapshots is append-only';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_prevent_snapshot_removal' AND tgrelid = 'cdp_profiles'::regclass) THEN
        CREATE TRIGGER trg_prevent_snapshot_removal BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW EXECUTE FUNCTION prevent_snapshot_removal();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cdp_profiles_primary_email ON cdp_profiles (tenant_id, primary_email);
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_identities ON cdp_profiles USING GIN (identities);
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_segments ON cdp_profiles USING GIN (segments jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_content_keywords ON cdp_profiles USING GIN (content_keywords);

ALTER TABLE cdp_profiles ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'cdp_profiles_tenant_rls' AND tablename = 'cdp_profiles') THEN
        CREATE POLICY cdp_profiles_tenant_rls ON cdp_profiles
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
    END IF;
END $$;

-- ============================================================
-- 5. AGENTIC AI CORE: REGISTRY & TOOLS (Moved up to prevent FK errors)
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_agent_registry (
    agent_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    agent_name      TEXT NOT NULL, 
    model_provider  TEXT NOT NULL, 
    model_version   TEXT NOT NULL, 
    system_prompt   TEXT NOT NULL,
    temperature     NUMERIC(3,2) DEFAULT 0.0,
    status          TEXT DEFAULT 'active',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_agent_tools (
    tool_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES ai_agent_registry(agent_id) ON DELETE CASCADE,
    tool_name       TEXT NOT NULL, 
    description     TEXT NOT NULL,
    parameters_schema JSONB NOT NULL DEFAULT '{}'::jsonb, 
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_agent_registry_updated' AND tgrelid = 'ai_agent_registry'::regclass) THEN
        CREATE TRIGGER trg_agent_registry_updated BEFORE UPDATE ON ai_agent_registry FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

ALTER TABLE ai_agent_registry ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'agent_registry_tenant_rls' AND tablename = 'ai_agent_registry') THEN
        CREATE POLICY agent_registry_tenant_rls ON ai_agent_registry 
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
    END IF;
END $$;

-- ============================================================
-- 6. AGENTIC AI CORE: MEMORY & SYNTHESIS
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_agent_sessions (
    session_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    agent_id        UUID NOT NULL REFERENCES ai_agent_registry(agent_id) ON DELETE CASCADE,
    profile_id      TEXT REFERENCES cdp_profiles(profile_id) ON DELETE SET NULL,
    status          TEXT DEFAULT 'active', 
    context_data    JSONB DEFAULT '{}'::jsonb, 
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_agent_sessions_updated' AND tgrelid = 'ai_agent_sessions'::regclass) THEN
        CREATE TRIGGER trg_agent_sessions_updated BEFORE UPDATE ON ai_agent_sessions FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS ai_agent_messages (
    message_id      BIGSERIAL PRIMARY KEY,
    session_id      UUID NOT NULL REFERENCES ai_agent_sessions(session_id) ON DELETE CASCADE,
    role            TEXT NOT NULL, 
    content         TEXT,
    tool_calls      JSONB,         
    tool_results    JSONB,         
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_session ON ai_agent_messages(session_id, created_at DESC);

-- ============================================================
-- 7. CAMPAIGN (STRATEGY)
-- ============================================================
CREATE TABLE IF NOT EXISTS campaign (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    campaign_id    TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    campaign_code  TEXT NOT NULL, 
    campaign_name  TEXT NOT NULL,
    objective      TEXT, 
    status         TEXT NOT NULL DEFAULT 'active',
    start_at       TIMESTAMPTZ,
    end_at         TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_campaign PRIMARY KEY (tenant_id, campaign_id),
    CONSTRAINT uq_campaign_code UNIQUE (tenant_id, campaign_code)
);

-- ============================================================
-- 8. MARKETING EVENT (EXECUTION)
-- ============================================================
CREATE TABLE IF NOT EXISTS marketing_event (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    marketing_event_id       TEXT NOT NULL, 
    campaign_id    TEXT, 
    marketing_event_name     TEXT NOT NULL, 
    marketing_event_type     TEXT NOT NULL, 
    marketing_event_channel  TEXT NOT NULL, 
    start_at       TIMESTAMPTZ NOT NULL, 
    end_at         TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'planned',
    embedding      VECTOR(1536),
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_marketing_event PRIMARY KEY (tenant_id, marketing_event_id),
    CONSTRAINT fk_marketing_event_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
) PARTITION BY HASH (tenant_id);

DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS marketing_event_p%s PARTITION OF marketing_event FOR VALUES WITH (MODULUS 16, REMAINDER %s);', i, i);
    END LOOP;
END $$;

-- ============================================================
-- 9. SEGMENT SNAPSHOTS & MEMBERS
-- ============================================================
CREATE TABLE IF NOT EXISTS segment_snapshot (
    tenant_id        UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    snapshot_id      TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    segment_name     TEXT NOT NULL,
    segment_version  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_segment_snapshot PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE TABLE IF NOT EXISTS segment_snapshot_member (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    snapshot_id  TEXT NOT NULL,
    profile_id   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_segment_snapshot_member PRIMARY KEY (tenant_id, snapshot_id, profile_id),
    CONSTRAINT fk_snapshot_member_snapshot FOREIGN KEY (tenant_id, snapshot_id) REFERENCES segment_snapshot (tenant_id, snapshot_id) ON DELETE CASCADE,
    CONSTRAINT fk_snapshot_member_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
);

-- ============================================================
-- 10. ALERT CENTER - REFERENCE DATA
-- ============================================================
CREATE TABLE IF NOT EXISTS trackable_entities (
    entity_id       BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE, 
    entity_code     VARCHAR(50) NOT NULL, 
    entity_name     TEXT NOT NULL,
    entity_type     VARCHAR(50) NOT NULL, 
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_entity_code UNIQUE (tenant_id, entity_code)
);

CREATE TABLE IF NOT EXISTS entity_states (
    entity_code     VARCHAR(50) PRIMARY KEY,
    current_value   NUMERIC(18, 5), 
    change_metric   NUMERIC(5, 2),
    last_updated    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 11. ALERT CENTER - RULES ENGINE
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_source_enum') THEN
        CREATE TYPE alert_source_enum AS ENUM ('USER_MANUAL', 'AI_AGENT');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alert_status_enum') THEN
        CREATE TYPE alert_status_enum AS ENUM ('ACTIVE', 'PAUSED', 'TRIGGERED');
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id         VARCHAR(64) NOT NULL, 
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      TEXT NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    symbol          VARCHAR(20) NOT NULL, 
    alert_type      VARCHAR(50) NOT NULL, 
    source          alert_source_enum DEFAULT 'USER_MANUAL',
    condition_logic JSONB NOT NULL,
    status          alert_status_enum DEFAULT 'ACTIVE',
    frequency       VARCHAR(50) DEFAULT 'ONCE', 
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT pk_alert_rules PRIMARY KEY (tenant_id, rule_id)
);

CREATE OR REPLACE FUNCTION generate_alert_rule_hash()
RETURNS TRIGGER AS $$
BEGIN
    NEW.rule_id := encode(
        digest(
            lower(concat_ws('||', NEW.tenant_id::text, NEW.profile_id, NEW.symbol, NEW.alert_type, NEW.frequency, NEW.condition_logic::text)),
            'sha256'
        ),
        'hex'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_alert_rules_hash' AND tgrelid = 'alert_rules'::regclass) THEN
        CREATE TRIGGER trg_alert_rules_hash BEFORE INSERT ON alert_rules
        FOR EACH ROW EXECUTE FUNCTION generate_alert_rule_hash();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_alert_rules_updated_at' AND tgrelid = 'alert_rules'::regclass) THEN
        CREATE TRIGGER trg_alert_rules_updated_at BEFORE UPDATE ON alert_rules
        FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_alert_rules_worker ON alert_rules (symbol, status) WHERE status = 'ACTIVE';

ALTER TABLE alert_rules ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'alert_rules_tenant_rls' AND tablename = 'alert_rules') THEN
        CREATE POLICY alert_rules_tenant_rls ON alert_rules
        USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
        WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);
    END IF;
END $$;

-- ============================================================
-- 12. ALERT CENTER - SEMANTIC NEWS & SIGNALS
-- ============================================================
CREATE TABLE IF NOT EXISTS news_feed (
    news_id         BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    content         TEXT,
    url             TEXT,
    related_symbols VARCHAR(20)[],
    sentiment_score NUMERIC(3,2),
    content_embedding vector(1536),
    published_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_embedding ON news_feed USING hnsw (content_embedding vector_cosine_ops);

-- ============================================================
-- 13. AGENT TASK (AI DECISION TRACE)
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_task (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    task_id      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    agent_name   TEXT NOT NULL, 
    task_type    TEXT NOT NULL,
    task_goal    TEXT,

    -- Linkage to previously created ai_agent_sessions table
    session_id UUID REFERENCES ai_agent_sessions(session_id) ON DELETE CASCADE,
    fallback_triggered BOOLEAN DEFAULT FALSE,
    reasoning_summary TEXT,
    reasoning_trace   JSONB,

    status       TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    
    -- FIXED BUG: Swapped invalid ; for ,
    execution_latency_ms INTEGER, 

    campaign_id  TEXT,
    marketing_event_id TEXT,
    snapshot_id  TEXT, 
    related_news_id BIGINT REFERENCES news_feed(news_id),

    CONSTRAINT fk_agent_task_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
);

-- ============================================================
-- 14. DELIVERY LOG (EXECUTION TRUTH)
-- ============================================================
CREATE TABLE IF NOT EXISTS delivery_log (
    tenant_id     UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    delivery_id   BIGSERIAL PRIMARY KEY,
    campaign_id   TEXT, 
    marketing_event_id TEXT NOT NULL,
    profile_id    TEXT NOT NULL, 
    channel       TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    provider_response JSONB,
    sent_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 15. EMBEDDING QUEUE
-- ============================================================
CREATE TABLE IF NOT EXISTS embedding_job (
    job_id      BIGSERIAL PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    marketing_event_id TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 16. BEHAVIORAL EVENTS (THE FEEDBACK LOOP)
-- ============================================================
CREATE TABLE IF NOT EXISTS behavioral_events (
    event_id        TEXT NOT NULL, 
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      TEXT NOT NULL, 
    event_metric_name TEXT NOT NULL, 
    entity_type     TEXT, 
    entity_id       TEXT, 
    sentiment_val   INTEGER DEFAULT 0, 
    meta_data       JSONB DEFAULT '{}'::jsonb, 
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT fk_behavioral_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
) PARTITION BY RANGE (created_at);

DO $$
DECLARE
    start_date DATE := date_trunc('month', now());
    partition_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..11 LOOP
        partition_date := start_date + (i || ' month')::interval;
        partition_name := 'behavioral_events_' || to_char(partition_date, 'YYYY_MM');
        EXECUTE format('CREATE TABLE IF NOT EXISTS %I PARTITION OF behavioral_events FOR VALUES FROM (%L) TO (%L)', partition_name, partition_date, partition_date + '1 month'::interval);
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_behavioral_profile_time ON behavioral_events (profile_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_behavioral_entity ON behavioral_events (entity_type, entity_id);

ALTER TABLE behavioral_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY behavioral_events_tenant_rls ON behavioral_events
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- ============================================================
-- 17. CONSENT MANAGEMENT
-- ============================================================
CREATE TABLE IF NOT EXISTS consent_management (
    consent_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      TEXT NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    channel         TEXT NOT NULL,           
    is_allowed      BOOLEAN NOT NULL DEFAULT FALSE,
    source          TEXT,                    
    legal_basis     TEXT,                    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_consent_profile_channel UNIQUE (tenant_id, profile_id, channel)
);

CREATE INDEX IF NOT EXISTS idx_consent_tenant_profile ON consent_management (tenant_id, profile_id);
CREATE INDEX IF NOT EXISTS idx_consent_channel_allowed ON consent_management (channel, is_allowed);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_consent_updated' AND tgrelid = 'consent_management'::regclass) THEN
        CREATE TRIGGER trg_consent_updated BEFORE UPDATE ON consent_management FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ============================================================
-- 18. DATA SOURCES
-- ============================================================
CREATE TABLE IF NOT EXISTS data_sources (
    source_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    source_name     TEXT NOT NULL,
    source_type     TEXT NOT NULL,        
    connection_ref  TEXT,                 
    sync_frequency  INTERVAL,             
    last_synced_at  TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_tenant_source_name UNIQUE (tenant_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_data_sources_tenant ON data_sources (tenant_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_active ON data_sources (is_active);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_data_sources_updated' AND tgrelid = 'data_sources'::regclass) THEN
        CREATE TRIGGER trg_data_sources_updated BEFORE UPDATE ON data_sources FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ============================================================
-- 19. ACTIVATION EXPERIMENTS
-- ============================================================
CREATE TABLE IF NOT EXISTS activation_experiments (
    experiment_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    campaign_id        TEXT NOT NULL,
    variant_name       TEXT NOT NULL,        
    exposure_count     INT NOT NULL DEFAULT 0,
    conversion_count   INT NOT NULL DEFAULT 0,
    metric_name        TEXT,                 
    started_at         TIMESTAMPTZ,
    ended_at           TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_experiment_variant UNIQUE (tenant_id, campaign_id, variant_name)
);

CREATE INDEX IF NOT EXISTS idx_experiments_campaign ON activation_experiments (tenant_id, campaign_id);
CREATE INDEX IF NOT EXISTS idx_experiments_variant ON activation_experiments (variant_name);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_activation_experiments_updated' AND tgrelid = 'activation_experiments'::regclass) THEN
        CREATE TRIGGER trg_activation_experiments_updated BEFORE UPDATE ON activation_experiments FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ============================================================
-- 20. MESSAGE TEMPLATES
-- ============================================================
CREATE TABLE IF NOT EXISTS message_templates (
    template_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    channel             TEXT NOT NULL,   
    template_name       TEXT NOT NULL,
    subject_template    TEXT,            
    body_template       TEXT NOT NULL,    
    template_engine     TEXT NOT NULL DEFAULT 'jinja2',  
    language_code       TEXT DEFAULT 'vi',               
    metadata            JSONB NOT NULL DEFAULT '{}',     
    status              TEXT NOT NULL DEFAULT 'draft',   
    version             INT NOT NULL DEFAULT 1,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_template_name_version UNIQUE (tenant_id, channel, template_name, version)
);

CREATE INDEX IF NOT EXISTS idx_message_templates_tenant ON message_templates (tenant_id);
CREATE INDEX IF NOT EXISTS idx_message_templates_channel ON message_templates (channel);
CREATE INDEX IF NOT EXISTS idx_message_templates_status ON message_templates (status);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_message_templates_updated' AND tgrelid = 'message_templates'::regclass) THEN
        CREATE TRIGGER trg_message_templates_updated BEFORE UPDATE ON message_templates FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ============================================================
-- 21. ACTIVATION OUTCOMES
-- ============================================================
CREATE TABLE IF NOT EXISTS activation_outcomes (
    outcome_id        BIGSERIAL PRIMARY KEY,
    tenant_id         UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    delivery_id       BIGINT NOT NULL REFERENCES delivery_log(delivery_id) ON DELETE CASCADE,
    profile_id        TEXT NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    outcome_type      TEXT NOT NULL,    
    outcome_value     NUMERIC,           
    occurred_at       TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_outcomes_tenant_delivery ON activation_outcomes (tenant_id, delivery_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_profile_time ON activation_outcomes (profile_id, occurred_at);

-- ============================================================
-- 22. EVENT METRICS 
-- ============================================================
CREATE TABLE IF NOT EXISTS event_metrics (
    tenant_id             UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    journey_map_id         TEXT NOT NULL,
    event_name             TEXT NOT NULL,
    event_metric_id        TEXT GENERATED ALWAYS AS (tenant_id || ':' || journey_map_id || ':' || event_name) STORED NOT NULL,
    event_label            TEXT NOT NULL,
    funnel_stage_id        TEXT NOT NULL,
    flow_name              TEXT NOT NULL,
    journey_stage          SMALLINT,
    score                  INTEGER NOT NULL DEFAULT 0,
    cumulative_point       INTEGER NOT NULL DEFAULT 0,
    score_model            SMALLINT,
    data_type              SMALLINT,
    show_in_observer_js    BOOLEAN NOT NULL DEFAULT FALSE,
    system_metric          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_event_metrics PRIMARY KEY (tenant_id, journey_map_id, event_name)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_event_metrics_updated' AND tgrelid = 'event_metrics'::regclass) THEN
        CREATE TRIGGER trg_event_metrics_updated BEFORE UPDATE ON event_metrics FOR EACH ROW EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_bem_tenant_event ON event_metrics (tenant_id, event_name);
CREATE INDEX IF NOT EXISTS idx_bem_tenant_flow ON event_metrics (tenant_id, flow_name);
CREATE INDEX IF NOT EXISTS idx_bem_event_metric_id ON event_metrics (tenant_id, event_metric_id);
CREATE INDEX IF NOT EXISTS idx_bem_funnel_stage ON event_metrics (tenant_id, funnel_stage_id);
CREATE INDEX IF NOT EXISTS idx_bem_journey_map ON event_metrics (tenant_id, journey_map_id);
CREATE INDEX IF NOT EXISTS idx_bem_created_at ON event_metrics (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_bem_system_metric ON event_metrics (tenant_id, system_metric);

-- ============================================================
-- 23. PRODUCT RECOMMENDATIONS
-- ============================================================
CREATE TABLE IF NOT EXISTS product_recommendations (
    tenant_id              UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id             TEXT NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    journey_map_id         TEXT NOT NULL,
    journey_stage_id       TEXT NOT NULL, 
    recommendation_context TEXT,           
    product_id             TEXT NOT NULL,
    product_type           TEXT NOT NULL, 
    product_url            TEXT DEFAULT NULL, 
    raw_score              NUMERIC(10,4) NOT NULL DEFAULT 0,
    interest_score         NUMERIC(5,4)  NOT NULL DEFAULT 0, 
    rank_position          INTEGER,
    recommendation_model   TEXT NOT NULL, 
    model_version          TEXT,
    reason_codes           JSONB,          
    last_interaction_at    TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_product_recommendations PRIMARY KEY (tenant_id, profile_id, journey_map_id, journey_stage_id, product_id, recommendation_model),
    CONSTRAINT chk_interest_score_range CHECK (interest_score >= 0 AND interest_score <= 1)
);

CREATE INDEX IF NOT EXISTS idx_pr_profile ON product_recommendations (tenant_id, profile_id);
CREATE INDEX IF NOT EXISTS idx_pr_journey_stage ON product_recommendations (tenant_id, journey_map_id, journey_stage_id);
CREATE INDEX IF NOT EXISTS idx_pr_profile_rank ON product_recommendations (tenant_id, profile_id, interest_score DESC, rank_position);
CREATE INDEX IF NOT EXISTS idx_pr_model ON product_recommendations (tenant_id, recommendation_model);
CREATE INDEX IF NOT EXISTS idx_pr_product ON product_recommendations (tenant_id, product_id);
CREATE INDEX IF NOT EXISTS idx_pr_updated_at ON product_recommendations (tenant_id, updated_at);

-- ============================================================
-- 24. SYSTEM BOOTSTRAP: Safely bootstrap 'master' tenant
-- ============================================================
ALTER TABLE tenant DISABLE ROW LEVEL SECURITY;

INSERT INTO tenant (tenant_name, status, keycloak_realm, keycloak_client_id)
VALUES ('master', 'active', 'leo-master', 'leo-activation')
ON CONFLICT (keycloak_realm, tenant_name) DO NOTHING;

ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT tenant_id INTO STRICT v_tenant_id FROM tenant WHERE tenant_name = 'master' AND keycloak_realm = 'leo-master';
    PERFORM set_config('app.current_tenant_id', v_tenant_id::text, false);
    RAISE NOTICE 'Session configured for tenant=master, tenant_id=%', v_tenant_id;
END $$;

-- ============================================================
-- 25. KNOWLEDGE BASE (Partitioned RAG Repository)
-- ============================================================
CREATE TABLE IF NOT EXISTS knowledge_base (
    tenant_id              UUID NOT NULL, 
    id                     UUID NOT NULL DEFAULT gen_random_uuid(),
    language               VARCHAR(10) NOT NULL DEFAULT 'en',
    domain                 VARCHAR(50), 
    category               VARCHAR(50), 
    keyword                VARCHAR(255),
    content                TEXT NOT NULL,
    content_hash           BYTEA GENERATED ALWAYS AS (digest(content, 'sha256')) STORED,
    source                 TEXT,
    metadata               JSONB DEFAULT '{}'::jsonb,
    embedding              halfvec(1536), 
    is_active              BOOLEAN DEFAULT TRUE,
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, id)
) PARTITION BY HASH (tenant_id);

COMMENT ON TABLE knowledge_base IS 'Core RAG repository for AI Agent knowledge, partitioned for 1B row scale.';

-- Dynamic Configuration Block (Partitions & Vector Index)
DO $$
DECLARE
    c_num_partitions       CONSTANT INT := 8; 
    c_hnsw_m               CONSTANT INT := 16;  
    c_hnsw_ef_construction CONSTANT INT := 64;  
    i INT;
BEGIN
    FOR i IN 0..(c_num_partitions - 1) LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS knowledge_base_p%s PARTITION OF knowledge_base FOR VALUES WITH (MODULUS %s, REMAINDER %s);', i, c_num_partitions, i);
    END LOOP;

    IF NOT EXISTS (SELECT 1 FROM pg_class c WHERE c.relname = 'idx_kb_embedding_hnsw') THEN
        EXECUTE format('CREATE INDEX idx_kb_embedding_hnsw ON knowledge_base USING hnsw (embedding halfvec_cosine_ops) WITH (m = %s, ef_construction = %s);', c_hnsw_m, c_hnsw_ef_construction);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uniq_kb_tenant_hash ON knowledge_base (tenant_id, category, content_hash);
CREATE INDEX IF NOT EXISTS idx_kb_tenant_domain_lang ON knowledge_base (tenant_id, domain, language) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_kb_keyword ON knowledge_base (tenant_id, keyword);
CREATE INDEX IF NOT EXISTS idx_kb_metadata_gin ON knowledge_base USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_kb_content_fts ON knowledge_base USING GIN (to_tsvector('simple', content));

-- =========================
-- END OF SCHEMA.SQL
-- =========================