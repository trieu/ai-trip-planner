-- ============================================================
-- LEO Data Activation & Alert Center – Unified Database Schema
-- Database: PostgreSQL 16+
-- Architecture: Multi-tenant, Event-Driven, Hybrid (SQL + Vector + Graph)
-- ============================================================

-- =========================
-- 1. REQUIRED EXTENSIONS
-- =========================
-- crypto: Used for gen_random_uuid() and hashing (SHA256) for idempotency.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- vector: Enables high-dimensional vector storage for RAG and Semantic Search.
CREATE EXTENSION IF NOT EXISTS vector;
-- citext: "Case-Insensitive Text" simplifies email/username comparisons.
CREATE EXTENSION IF NOT EXISTS citext;
-- age: Apache AGE for Graph Database capabilities (Nodes/Edges within Postgres).
CREATE EXTENSION IF NOT EXISTS age;
-- postgis: Spatial data support (if needed for geo-targeting in campaigns).
CREATE EXTENSION IF NOT EXISTS postgis;

-- Load AGE functionality and set path to include graph catalog
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- =========================
-- 2. SHARED UTILITIES
-- =========================

-- Function: Auto-update 'updated_at' timestamp
-- Usage: Applied via trigger to all mutable tables to track modification time.
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- =========================
-- 3. TENANT (CORE NAMESPACE, KEYCLOAK-INTEGRATED)
-- =========================
-- The root of the multi-tenant architecture. 
-- Tenant ID remains UUID to ensure global uniqueness across distributed systems.

-- =========================
-- TENANT (KEYCLOAK-INTEGRATED)
-- =========================
CREATE TABLE IF NOT EXISTS tenant (
    tenant_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_name         TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'active', -- active, suspended, archived

    -- Keycloak integration
    keycloak_realm      TEXT NOT NULL,        -- e.g. leo-prod, leo-staging
    keycloak_client_id  TEXT NOT NULL,        -- e.g. leo-activation
    keycloak_org_id     TEXT,                 -- optional: Keycloak Organization / Group ID

    -- Metadata
    metadata            JSONB NOT NULL DEFAULT '{}',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_tenant_keycloak_realm
        UNIQUE (keycloak_realm, tenant_name)
);

-- Enable RLS
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;

-- Allow SELECT only for current tenant
CREATE POLICY tenant_select_policy
ON tenant
FOR SELECT
USING (
    tenant_id = current_setting('app.current_tenant_id', true)::uuid
);

-- Allow INSERT / UPDATE WITHOUT tenant_id check
-- Tenant is a root entity and must be bootstrapable
CREATE POLICY tenant_insert_policy
ON tenant
FOR INSERT
WITH CHECK (true);

CREATE POLICY tenant_update_policy
ON tenant
FOR UPDATE
WITH CHECK (true);



-- =========================
-- Trigger: Maintain updated_at
-- =========================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_tenant_updated_at'
          AND tgrelid = 'tenant'::regclass
    ) THEN
        CREATE TRIGGER trg_tenant_updated_at
        BEFORE UPDATE ON tenant
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- Example (application side):
-- SET app.current_tenant_id = '<tenant-uuid>';



-- ============================================================
-- 4. CDP PROFILES (The "User" Entity)
-- Core unified customer profile table
-- Source of truth synchronized from ArangoDB → PostgreSQL
-- ============================================================
-- Design goals:
--   • Lossless sync from ArangoProfile (extra fields ignored upstream)
--   • Human-readable + AI-readable
--   • JSON-first where cardinality is unbounded
--   • Append-only semantics enforced at application / trigger level
-- ============================================================

CREATE TABLE IF NOT EXISTS cdp_profiles (
    -- =====================================================
    -- MULTI-TENANCY
    -- =====================================================
    tenant_id UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    -- Example: "8c2e6c4d-9c3b-4c8a-9b6a-9b8c0b6e2e91"

    -- =====================================================
    -- CORE IDENTITY
    -- =====================================================
    profile_id TEXT PRIMARY KEY,
    -- Source: Arango `_key`
    -- Example: "U_NAM_INVESTOR"

    identities JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- All known identifiers across systems
    -- Synced from Arango `identities`
    -- Example:
    -- ["crm:12345", "email:nam@gmail.com", "phone:+84901234567"]

    -- =====================================================
    -- CONTACT INFORMATION
    -- =====================================================
    primary_email CITEXT,
    -- Source: primaryEmail
    -- Example: "nam@gmail.com"

    secondary_emails JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: secondaryEmails
    -- Example: ["nam.work@gmail.com", "nam.invest@gmail.com"]

    primary_phone TEXT,
    -- Source: primaryPhone
    -- Example: "+84901234567"

    secondary_phones JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: secondaryPhones
    -- Example: ["+84908887777"]

    -- =====================================================
    -- PERSONAL & LOCATION DATA
    -- =====================================================
    first_name TEXT,
    -- Source: firstName
    -- Example: "Nam"

    last_name TEXT,
    -- Source: lastName
    -- Example: "Nguyen"

    living_location TEXT,
    -- Source: livingLocation
    -- Example: "Vietnam"

    living_country TEXT,
    -- Source: livingCountry
    -- Example: "VN"

    living_city TEXT,
    -- Source: livingCity
    -- Example: "Ho Chi Minh City"

    -- =====================================================
    -- ENRICHMENT & INTEREST SIGNALS
    -- =====================================================
    job_titles JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: jobTitles
    -- Example: ["Investor", "Founder"]

    data_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: dataLabels
    -- Example: ["VIP", "HIGH_NET_WORTH"]

    content_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: contentKeywords
    -- Example: ["value investing", "dividends", "VNM"]

    media_channels JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: mediaChannels
    -- Example: ["EMAIL", "ZALO", "PUSH"]

    behavioral_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: behavioralEvents (semantic labels, not raw events)
    -- Example: ["VIEW_STOCK", "READ_NEWS", "CLICK_ALERT"]

    -- =====================================================
    -- SEGMENTATION & JOURNEYS
    -- =====================================================
    segments JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: inSegments
    -- Example:
    -- [
    --   { "id": "VIP", "name": "High Value Investor" }
    -- ]

    journey_maps JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: inJourneyMaps
    -- Example:
    -- [
    --   { "id": "J01", "name": "Investor Onboarding", "funnelIndex": 2 }
    -- ]

    segment_snapshots JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Historical segment membership (append-only)
    -- Used for audit & AI learning

    -- =====================================================
    -- STATISTICS & TOUCHPOINTS
    -- =====================================================
    event_statistics JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Source: eventStatistics
    -- Example:
    -- { "id_default_journey-page-view": 120, "id_default_journey-ask-question": 34, "id_default_journey-purchase": 2 }

    top_engaged_touchpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- Source: topEngagedTouchpoints
    -- Example:
    -- [
    --   {
    --     "_key": "tp_01",
    --     "hostname": "vnexpress.net",
    --     "name": "Market News",
    --     "url": "https://vnexpress.net",
    --     "parentId": "news_group"
    --   }
    -- ]

    -- =====================================================
    -- PORTFOLIO SNAPSHOT (AUTHORITATIVE CURRENT STATE)
    -- =====================================================
    portfolio_snapshot JSONB DEFAULT '{}'::jsonb,
    -- Example:
    -- {
    --   "cash_available": 200000000,
    --   "positions": [
    --     {
    --       "symbol": "VNM",
    --       "quantity": 1000,
    --       "avg_price": 70000
    --     }
    --   ]
    -- }

    portfolio_risk_score NUMERIC(3,2),
    -- Normalized risk score [0..1]
    -- Example: 0.35

    portfolio_last_evaluated_at TIMESTAMPTZ,
    -- When AI last evaluated the portfolio

    -- =====================================================
    -- AI LONG-TERM MEMORY
    -- =====================================================
    interest_embedding vector(1536),
    -- Aggregated semantic embedding of long-term interests
    -- Used for RAG, recommendations, advisory signals

    -- =====================================================
    -- AUDIT
    -- =====================================================
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    ext_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    status   TEXT NOT NULL DEFAULT 'active', -- active, suspended, archived

    -- =====================================================
    -- CONSTRAINTS
    -- =====================================================
    CONSTRAINT uq_cdp_profile_identity UNIQUE (tenant_id, profile_id)
);

-- ============================================================
-- CDP_PROFILES – TRIGGERS, GUARDS, INDEXES, SECURITY
-- ============================================================

-- ------------------------------------------------------------
-- Trigger: Maintain updated_at automatically
-- ------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_cdp_profiles_updated_at'
          AND tgrelid = 'cdp_profiles'::regclass
    ) THEN
        CREATE TRIGGER trg_cdp_profiles_updated_at
        BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp();
    END IF;
END $$;

-- ------------------------------------------------------------
-- Logic Guard: segment_snapshots must be append-only
-- ------------------------------------------------------------
-- Rationale:
--   segment_snapshots represents historical truth.
--   AI learning & audit rely on monotonic growth.
--   Deletions or truncations indicate data corruption.
CREATE OR REPLACE FUNCTION prevent_snapshot_removal()
RETURNS TRIGGER AS $$
BEGIN
    IF jsonb_array_length(NEW.segment_snapshots)
       < jsonb_array_length(OLD.segment_snapshots) THEN
        RAISE EXCEPTION
            'Data Integrity Violation: segment_snapshots is append-only';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgname = 'trg_prevent_snapshot_removal'
          AND tgrelid = 'cdp_profiles'::regclass
    ) THEN
        CREATE TRIGGER trg_prevent_snapshot_removal
        BEFORE UPDATE ON cdp_profiles
        FOR EACH ROW
        EXECUTE FUNCTION prevent_snapshot_removal();
    END IF;
END $$;

-- ------------------------------------------------------------
-- INDEXES (Aligned with current schema + Arango sync model)
-- ------------------------------------------------------------

-- Fast lookup by primary email within tenant
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_primary_email
    ON cdp_profiles (tenant_id, primary_email);

-- Fast lookup by identities (cross-system resolution)
-- Example queries:
--   identities @> '["email:nam@gmail.com"]'
--   identities ? 'crm:12345'
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_identities
    ON cdp_profiles
    USING GIN (identities);

-- Fast segment membership queries
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_segments
    ON cdp_profiles
    USING GIN (segments jsonb_path_ops);

-- Optional: accelerate keyword / enrichment searches
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_content_keywords
    ON cdp_profiles
    USING GIN (content_keywords);

-- Optional: portfolio-level filtering (JSON predicates)
CREATE INDEX IF NOT EXISTS idx_cdp_profiles_portfolio
    ON cdp_profiles
    USING GIN (portfolio_snapshot);

-- ------------------------------------------------------------
-- SECURITY: Row Level Security (RLS)
-- ------------------------------------------------------------
-- Enforced by app.current_tenant_id session variable
ALTER TABLE cdp_profiles ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_policies
        WHERE policyname = 'cdp_profiles_tenant_rls'
          AND tablename = 'cdp_profiles'
    ) THEN
        CREATE POLICY cdp_profiles_tenant_rls
        ON cdp_profiles
        USING (
            tenant_id = current_setting('app.current_tenant_id', true)::uuid
        )
        WITH CHECK (
            tenant_id = current_setting('app.current_tenant_id', true)::uuid
        );
    END IF;
END $$;



-- ============================================================
-- 5. CAMPAIGN (STRATEGY)
-- ============================================================
-- Marketing initiatives container.
-- ID Type: TEXT
CREATE TABLE IF NOT EXISTS campaign (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    campaign_id    TEXT NOT NULL DEFAULT gen_random_uuid()::text,
    
    campaign_code  TEXT NOT NULL, -- Human readable code (e.g., 'SUMMER-2026')
    campaign_name  TEXT NOT NULL,
    objective      TEXT, -- 'AWARENESS', 'CONVERSION', etc.
    status         TEXT NOT NULL DEFAULT 'active',
    
    start_at       TIMESTAMPTZ,
    end_at         TIMESTAMPTZ,
    
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_campaign PRIMARY KEY (tenant_id, campaign_id),
    CONSTRAINT uq_campaign_code UNIQUE (tenant_id, campaign_code)
);

-- ============================================================
-- 6. MARKETING EVENT (EXECUTION)
-- ============================================================
-- Specific actions within a campaign (e.g., "Send Email Tuesday").
-- Partitioned by Tenant for scalability.
CREATE TABLE IF NOT EXISTS marketing_event (
    tenant_id      UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    marketing_event_id       TEXT NOT NULL, -- Client-provided or generated ID
    campaign_id    TEXT, -- Reference to Parent Campaign
    
    marketing_event_name     TEXT NOT NULL, -- e.g. "Email Blast June 2024"
    marketing_event_type     TEXT NOT NULL, -- 'EMAIL', 'SMS', 'PUSH', 'IN_APP'
    marketing_event_channel  TEXT NOT NULL, -- 'EVENT', 'PROMOTIONAL', 'TRANSACTIONAL'
    
    start_at       TIMESTAMPTZ NOT NULL, 
    end_at         TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL DEFAULT 'planned',
    
    -- AI Context: Embedding of the event description for "Campaign RAG"
    embedding      VECTOR(1536),
    embedding_status TEXT NOT NULL DEFAULT 'pending',
    
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_marketing_event PRIMARY KEY (tenant_id, marketing_event_id),
    CONSTRAINT fk_marketing_event_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
) PARTITION BY HASH (tenant_id);

-- Create Partitions (Modulus 16)
DO $$
BEGIN
    FOR i IN 0..15 LOOP
        EXECUTE format('CREATE TABLE IF NOT EXISTS marketing_event_p%s PARTITION OF marketing_event FOR VALUES WITH (MODULUS 16, REMAINDER %s);', i, i);
    END LOOP;
END $$;

-- ============================================================
-- 7. SEGMENT SNAPSHOTS & MEMBERS
-- ============================================================
-- Static lists of users captured at a specific point in time.
-- ID Type: TEXT

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
    profile_id   TEXT NOT NULL, -- FK to cdp_profiles
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT pk_segment_snapshot_member PRIMARY KEY (tenant_id, snapshot_id, profile_id),
    CONSTRAINT fk_snapshot_member_snapshot FOREIGN KEY (tenant_id, snapshot_id) REFERENCES segment_snapshot (tenant_id, snapshot_id) ON DELETE CASCADE,
    CONSTRAINT fk_snapshot_member_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
);

-- ============================================================
-- 8. ALERT CENTER - REFERENCE DATA
-- ============================================================

-- 8.1 Instruments (Assets/Books/Indices)
CREATE TABLE IF NOT EXISTS instruments (
    instrument_id   BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE, -- NULL = Global Asset
    
    symbol          VARCHAR(20) NOT NULL, -- e.g. 'AAPL', 'BTC-USD'
    name            TEXT NOT NULL,
    type            VARCHAR(50) NOT NULL, -- 'STOCK', 'CRYPTO', 'FX'
    sector          VARCHAR(100),
    meta_data       JSONB DEFAULT '{}'::jsonb,
    
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    CONSTRAINT uq_instrument_symbol UNIQUE (tenant_id, symbol)
);

-- 8.2 Real-time Market Snapshot
-- High-write throughput table.
CREATE TABLE IF NOT EXISTS market_snapshot (
    symbol          VARCHAR(20) PRIMARY KEY,
    price           NUMERIC(18, 5),
    change_percent  NUMERIC(5, 2),
    volume          BIGINT,
    last_updated    TIMESTAMPTZ DEFAULT now()
);

-- ============================================================
-- 9. ALERT CENTER - RULES ENGINE
-- ============================================================

-- Enums for Type Safety
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
    -- ID is a deterministic hash (TEXT/VARCHAR) based on the rule logic.
    rule_id         VARCHAR(64) NOT NULL, 
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    
    -- UPDATED: profile_id is now TEXT to match cdp_profiles PK
    profile_id      TEXT NOT NULL REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,
    
    -- Target Asset
    symbol          VARCHAR(20) NOT NULL, 
    
    -- Configuration
    alert_type      VARCHAR(50) NOT NULL, -- 'PRICE', 'NEWS', 'AI_SIGNAL'
    source          alert_source_enum DEFAULT 'USER_MANUAL',
    
    -- The Condition (e.g., {"operator": ">", "value": 150})
    condition_logic JSONB NOT NULL,
    
    status          alert_status_enum DEFAULT 'ACTIVE',
    frequency       VARCHAR(50) DEFAULT 'ONCE', 
    
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    
    -- Composite PK for multi-tenancy
    CONSTRAINT pk_alert_rules PRIMARY KEY (tenant_id, rule_id)
);

-- Idempotency Logic: Generate Hash ID based on Rule Content
-- Ensures we don't create duplicate rules for the same user/symbol/condition.
CREATE OR REPLACE FUNCTION generate_alert_rule_hash()
RETURNS TRIGGER AS $$
BEGIN
    NEW.rule_id := encode(
        digest(
            lower(concat_ws('||',
                NEW.tenant_id::text,
                NEW.profile_id, -- Already text
                NEW.symbol,
                NEW.alert_type,
                NEW.frequency,
                NEW.condition_logic::text 
            )),
            'sha256'
        ),
        'hex'
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for Hash and Timestamp
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

-- Index for the "Worker" that scans active rules
CREATE INDEX IF NOT EXISTS idx_alert_rules_worker 
ON alert_rules (symbol, status) 
WHERE status = 'ACTIVE';

-- RLS Policy
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
-- 10. ALERT CENTER - SEMANTIC NEWS & SIGNALS
-- ============================================================

CREATE TABLE IF NOT EXISTS news_feed (
    news_id         BIGSERIAL PRIMARY KEY,
    tenant_id       UUID REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    
    title           TEXT NOT NULL,
    content         TEXT,
    url             TEXT,
    
    -- Metadata extracted by AI
    related_symbols VARCHAR(20)[],
    sentiment_score NUMERIC(3,2),
    
    -- Hybrid Search: Vector Embedding
    content_embedding vector(1536),
    
    published_at    TIMESTAMPTZ DEFAULT now()
);

-- HNSW Index: High-performance vector similarity search
CREATE INDEX IF NOT EXISTS idx_news_embedding 
ON news_feed USING hnsw (content_embedding vector_cosine_ops);

-- ============================================================
-- 11. AGENT TASK (AI DECISION TRACE)
-- ============================================================
-- Logs AI reasoning and actions.
-- ID Type: TEXT
CREATE TABLE IF NOT EXISTS agent_task (
    tenant_id    UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    task_id      TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,

    agent_name   TEXT NOT NULL, 
    task_type    TEXT NOT NULL,
    task_goal    TEXT,

    -- Linkage to other entities (All converted to TEXT)
    campaign_id  TEXT,
    marketing_event_id     TEXT,
    snapshot_id  TEXT, 
    
    related_news_id BIGINT REFERENCES news_feed(news_id),

    -- Chain of Thought (CoT) storage
    reasoning_summary TEXT,
    reasoning_trace   JSONB,

    status       TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,

    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_agent_task_campaign FOREIGN KEY (tenant_id, campaign_id) 
        REFERENCES campaign (tenant_id, campaign_id) ON DELETE SET NULL
);

-- ============================================================
-- 12. DELIVERY LOG (EXECUTION TRUTH)
-- ============================================================
-- Final record of messages sent to users.
-- ID Type: TEXT where applicable.
CREATE TABLE IF NOT EXISTS delivery_log (
    tenant_id     UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    delivery_id   BIGSERIAL PRIMARY KEY,
    
    campaign_id   TEXT, -- FK to campaign
    marketing_event_id      TEXT NOT NULL,
    
    profile_id    TEXT NOT NULL, -- FK to cdp_profiles (TEXT)
    
    channel       TEXT NOT NULL,
    delivery_status TEXT NOT NULL,
    provider_response JSONB,
    
    sent_at       TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- 13. EMBEDDING QUEUE
-- ============================================================
-- Asynchronous queue for processing embeddings.
CREATE TABLE IF NOT EXISTS embedding_job (
    job_id      BIGSERIAL PRIMARY KEY,
    tenant_id   UUID NOT NULL,
    marketing_event_id    TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',
    attempts    INTEGER DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 14. BEHAVIORAL EVENTS (THE FEEDBACK LOOP)
-- ============================================================
-- Captures high-frequency user actions for AI training & triggering.
-- Partitioned by time (Monthly) because this table grows huge.

CREATE TABLE IF NOT EXISTS behavioral_events (
    event_id        TEXT NOT NULL, -- High throughput, avoid UUID overhead here if possible, or use UUIDv7
    tenant_id       UUID NOT NULL REFERENCES tenant(tenant_id) ON DELETE CASCADE,
    profile_id      TEXT NOT NULL, -- No FK constraint for write speed? Or keep FK for integrity. Let's keep FK.
    
    event_metric_name      TEXT NOT NULL, -- 
    
    -- Context: What did they interact with?
    entity_type     TEXT, -- 'NEWS', 'ALERT', 'ASSET', 'CAMPAIGN'
    entity_id       TEXT, -- The ID of the news/alert/asset
    
    -- AI Feedback: Did this interaction signal positive or negative interest?
    sentiment_val   INTEGER DEFAULT 0, -- +1 (Positive), -1 (Negative), 0 (Neutral)
    
    meta_data       JSONB DEFAULT '{}'::jsonb, -- Store URL clicked, device info, etc.
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    CONSTRAINT fk_behavioral_profile FOREIGN KEY (profile_id) REFERENCES cdp_profiles (profile_id) ON DELETE CASCADE
) PARTITION BY RANGE (created_at);

-- Create partitions for the next 12 months automatically
DO $$
DECLARE
    start_date DATE := date_trunc('month', now());
    partition_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..11 LOOP
        partition_date := start_date + (i || ' month')::interval;
        partition_name := 'behavioral_events_' || to_char(partition_date, 'YYYY_MM');
        
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF behavioral_events FOR VALUES FROM (%L) TO (%L)',
            partition_name,
            partition_date,
            partition_date + '1 month'::interval
        );
    END LOOP;
END $$;

-- Indexes for Analytics & AI Training
CREATE INDEX IF NOT EXISTS idx_behavioral_profile_time 
    ON behavioral_events (profile_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_behavioral_entity 
    ON behavioral_events (entity_type, entity_id);

-- RLS
ALTER TABLE behavioral_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY behavioral_events_tenant_rls ON behavioral_events
    USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid)
    WITH CHECK (tenant_id = current_setting('app.current_tenant_id', true)::uuid);


-- ============================================================
-- 15.  CONSENT MANAGEMENT (LEGAL COMPLIANCE)
-- ============================================================
-- Tracks user consents for various channels and purposes.
-- Supports GDPR / PDPA audits
-- ============================================================
CREATE TABLE IF NOT EXISTS consent_management (
    consent_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id       UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    profile_id      TEXT NOT NULL
        REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,

    channel         TEXT NOT NULL,           -- email, sms, web, push, whatsapp
    is_allowed      BOOLEAN NOT NULL DEFAULT FALSE,

    source          TEXT,                    -- CMP, API, form, import
    legal_basis     TEXT,                    -- gdpr_consent, legitimate_interest

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_consent_profile_channel
        UNIQUE (tenant_id, profile_id, channel)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_consent_tenant_profile
    ON consent_management (tenant_id, profile_id);

CREATE INDEX IF NOT EXISTS idx_consent_channel_allowed
    ON consent_management (channel, is_allowed);

-- Trigger
CREATE TRIGGER trg_consent_updated
BEFORE UPDATE ON consent_management
FOR EACH ROW EXECUTE FUNCTION update_timestamp();


-- =========================
-- 16. DATA SOURCES (INTEGRATIONS)
-- =========================
-- Tracks external data sources integrated into the CDP.
-- =========================
CREATE TABLE IF NOT EXISTS data_sources (
    source_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id       UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    source_name     TEXT NOT NULL,
    source_type     TEXT NOT NULL,        -- s3, postgresql, arango, api, webhook

    connection_ref  TEXT,                 -- secret ref / connection id
    sync_frequency  INTERVAL,             -- e.g. '1 hour', '1 day'
    last_synced_at  TIMESTAMPTZ,

    is_active       BOOLEAN NOT NULL DEFAULT TRUE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_tenant_source_name
        UNIQUE (tenant_id, source_name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_data_sources_tenant
    ON data_sources (tenant_id);

CREATE INDEX IF NOT EXISTS idx_data_sources_active
    ON data_sources (is_active);

-- Trigger
CREATE TRIGGER trg_data_sources_updated
BEFORE UPDATE ON data_sources
FOR EACH ROW EXECUTE FUNCTION update_timestamp();


-- =========================
-- 17. ACTIVATION EXPERIMENTS (A/B TESTING)
-- =========================
-- Tracks A/B experiments for marketing campaigns.
-- =========================
CREATE TABLE IF NOT EXISTS activation_experiments (
    experiment_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id          UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    campaign_id        TEXT NOT NULL,
    variant_name       TEXT NOT NULL,        -- A, B, control, treatment_1

    exposure_count     INT NOT NULL DEFAULT 0,
    conversion_count   INT NOT NULL DEFAULT 0,

    metric_name        TEXT,                 -- click, purchase, signup
    started_at         TIMESTAMPTZ,
    ended_at           TIMESTAMPTZ,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_experiment_variant
        UNIQUE (tenant_id, campaign_id, variant_name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_experiments_campaign
    ON activation_experiments (tenant_id, campaign_id);

CREATE INDEX IF NOT EXISTS idx_experiments_variant
    ON activation_experiments (variant_name);

-- Trigger
CREATE TRIGGER trg_activation_experiments_updated
BEFORE UPDATE ON activation_experiments
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- =========================
-- 18. MESSAGE TEMPLATES (MULTI-CHANNEL)
-- =========================
-- Stores reusable message templates for activation across channels
-- such as Email, Zalo OA, Web Push, App Push, WhatsApp, Telegram.
-- Templates are definitions only (intent level), not execution truth.
-- =========================
CREATE TABLE IF NOT EXISTS message_templates (
    template_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id           UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    channel             TEXT NOT NULL,   -- email, zalo_oa, web_push, app_push, whatsapp, telegram
    template_name       TEXT NOT NULL,

    subject_template    TEXT,            -- used for email / notification title
    body_template       TEXT NOT NULL,    -- main message body (HTML / Markdown / text)

    template_engine     TEXT NOT NULL DEFAULT 'jinja2',  -- jinja2, handlebars, liquid
    language_code       TEXT DEFAULT 'vi',               -- vi, en, th, id, etc.

    metadata            JSONB NOT NULL DEFAULT '{}',     -- buttons, deep_links, images, CTA, provider hints

    status              TEXT NOT NULL DEFAULT 'draft',   -- draft, approved, archived
    version             INT NOT NULL DEFAULT 1,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_template_name_version
        UNIQUE (tenant_id, channel, template_name, version)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_message_templates_tenant
    ON message_templates (tenant_id);

CREATE INDEX IF NOT EXISTS idx_message_templates_channel
    ON message_templates (channel);

CREATE INDEX IF NOT EXISTS idx_message_templates_status
    ON message_templates (status);

-- Trigger
CREATE TRIGGER trg_message_templates_updated
BEFORE UPDATE ON message_templates
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- =========================
-- 19. ACTIVATION OUTCOMES (ATTRIBUTION TRUTH)
-- =========================
-- Links a specific delivery to a concrete user outcome.
-- This table is append-only and represents attribution truth.
-- e.g: This activation of delivery (email / push / message) is credited with this outcome.
-- =========================
CREATE TABLE IF NOT EXISTS activation_outcomes (
    outcome_id        BIGSERIAL PRIMARY KEY,

    tenant_id         UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    delivery_id       BIGINT NOT NULL
        REFERENCES delivery_log(delivery_id) ON DELETE CASCADE,

    profile_id        TEXT NOT NULL
        REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,

    outcome_type      TEXT NOT NULL,    -- click, open, purchase, signup
    outcome_value     NUMERIC,           -- revenue, score, duration, etc.

    occurred_at       TIMESTAMPTZ NOT NULL,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_outcomes_tenant_delivery
    ON activation_outcomes (tenant_id, delivery_id);

CREATE INDEX IF NOT EXISTS idx_outcomes_profile_time
    ON activation_outcomes (profile_id, occurred_at);


-- ============================================================
-- 20. EVENT METRICS (EVENTS)
-- ============================================================
-- Defines event metric for events tracked via SDK / API.
-- These event's metadata is used for scoring, segmentation, and triggering.
-- ============================================================
CREATE TABLE IF NOT EXISTS event_metrics (
    -- Tenant isolation
    tenant_id             UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    -- Natural key (business-defined)
    journey_map_id         TEXT NOT NULL,
    event_name             TEXT NOT NULL,

    -- Deterministic derived identifier
    event_metric_id        TEXT GENERATED ALWAYS AS (
        tenant_id || ':' || journey_map_id || ':' || event_name
    ) STORED NOT NULL,

    -- Event metadata
    event_label            TEXT NOT NULL,

    -- Funnel / journey
    funnel_stage_id        TEXT NOT NULL,
    flow_name              TEXT NOT NULL,
    journey_stage          SMALLINT,

    -- Scoring
    score                  INTEGER NOT NULL DEFAULT 0,
    cumulative_point       INTEGER NOT NULL DEFAULT 0,
    score_model            SMALLINT,
    data_type              SMALLINT,

    -- Flags
    show_in_observer_js    BOOLEAN NOT NULL DEFAULT FALSE,
    system_metric          BOOLEAN NOT NULL DEFAULT FALSE,

    -- Timestamps
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT pk_event_metrics
        PRIMARY KEY (tenant_id, journey_map_id, event_name)
);

-- Trigger
CREATE TRIGGER trg_event_metrics_updated
BEFORE UPDATE ON event_metrics
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- Indexes
-- Fast event lookup (most common query)
CREATE INDEX IF NOT EXISTS idx_bem_tenant_event
    ON event_metrics (tenant_id, event_name);

-- Flow-based analytics & routing
CREATE INDEX IF NOT EXISTS idx_bem_tenant_flow
    ON event_metrics (tenant_id, flow_name);

-- Deterministic ID lookup (SDK / Kafka / API)
CREATE INDEX IF NOT EXISTS idx_bem_event_metric_id
    ON event_metrics (tenant_id, event_metric_id);

-- Funnel analytics
CREATE INDEX IF NOT EXISTS idx_bem_funnel_stage
    ON event_metrics (tenant_id, funnel_stage_id);

-- Journey map queries
CREATE INDEX IF NOT EXISTS idx_bem_journey_map
    ON event_metrics (tenant_id, journey_map_id);

-- Time-based scans (dashboards, audits)
CREATE INDEX IF NOT EXISTS idx_bem_created_at
    ON event_metrics (tenant_id, created_at);

-- System vs business metrics
CREATE INDEX IF NOT EXISTS idx_bem_system_metric
    ON event_metrics (tenant_id, system_metric);

-- ============================================================
-- 21. PRODUCT RECOMMENDATIONS (PERSONALIZATION)
-- ============================================================
-- Stores precomputed product recommendations per user profile.
-- Supports journey-aware and context-aware recommendations.
-- ============================================================
CREATE TABLE IF NOT EXISTS product_recommendations (
    -- Tenant isolation
    tenant_id              UUID NOT NULL
        REFERENCES tenant(tenant_id) ON DELETE CASCADE,

    -- Who
    profile_id        TEXT NOT NULL
        REFERENCES cdp_profiles(profile_id) ON DELETE CASCADE,

    -- Context
    journey_map_id          TEXT NOT NULL,
    journey_stage_id        TEXT NOT NULL, -- e.g. "new-customer"
    recommendation_context  TEXT,           -- homepage | email | in_app

    -- What
    product_id              TEXT NOT NULL,
    product_type            TEXT NOT NULL, -- stock | fund | sku | course
    product_url             TEXT DEFAULT NULL, -- the URL of product page

    -- Scoring (deterministic)
    raw_score               NUMERIC(10,4) NOT NULL DEFAULT 0,
    interest_score          NUMERIC(5,4)  NOT NULL DEFAULT 0, -- 0.0000 → 1.0000
    rank_position           INTEGER,

    -- Model / logic
    recommendation_model    TEXT NOT NULL, -- rule_v1 | ml_cf_v3
    model_version           TEXT,
    reason_codes            JSONB,          -- explainability

    -- Freshness
    last_interaction_at     TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT pk_product_recommendations
        PRIMARY KEY (
            tenant_id,
            profile_id,
            journey_map_id,
            journey_stage_id,
            product_id,
            recommendation_model
        ),

    CONSTRAINT chk_interest_score_range
        CHECK (interest_score >= 0 AND interest_score <= 1)
);

-- Primary read path: recommendations per profile
CREATE INDEX IF NOT EXISTS idx_pr_profile
    ON product_recommendations (tenant_id, profile_id);

-- Journey-aware personalization
CREATE INDEX IF NOT EXISTS idx_pr_journey_stage
    ON product_recommendations (
        tenant_id,
        journey_map_id,
        journey_stage_id
    );

-- Ranking & rendering (Top-N queries)
CREATE INDEX IF NOT EXISTS idx_pr_profile_rank
    ON product_recommendations (
        tenant_id,
        profile_id,
        interest_score DESC,
        rank_position
    );

-- Model comparison / experiments
CREATE INDEX IF NOT EXISTS idx_pr_model
    ON product_recommendations (
        tenant_id,
        recommendation_model
    );

-- Product analytics
CREATE INDEX IF NOT EXISTS idx_pr_product
    ON product_recommendations (
        tenant_id,
        product_id
    );

-- Freshness & cleanup
CREATE INDEX IF NOT EXISTS idx_pr_updated_at
    ON product_recommendations (
        tenant_id,
        updated_at
    );



-- ============================================================
-- 22. SYSTEM BOOTSTRAP: Safely bootstrap 'master' tenant
-- ============================================================

-- RLS-safe: temporarily disable RLS for bootstrap
ALTER TABLE tenant DISABLE ROW LEVEL SECURITY;

INSERT INTO tenant (
    tenant_name,
    status,
    keycloak_realm,
    keycloak_client_id
)
VALUES (
    'master',
    'active',
    'leo-master',
    'leo-activation'
)
ON CONFLICT (keycloak_realm, tenant_name) DO NOTHING;

-- Re-enable RLS immediately
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;

-- =========================
-- 2. Set session tenant context
-- =========================
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    -- Fetch exactly one tenant ID (deterministic)
    SELECT tenant_id
    INTO STRICT v_tenant_id
    FROM tenant
    WHERE tenant_name = 'master'
      AND keycloak_realm = 'leo-master';

    -- Set session-scoped tenant context (required for RLS)
    PERFORM set_config(
        'app.current_tenant_id',
        v_tenant_id::text,
        false
    );

    RAISE NOTICE 'Session configured for tenant=master, tenant_id=%', v_tenant_id;
END $$;


-- ============================================================
-- 23. Knowledge Base (Partitioned AI-ENABLED CONTENT REPOSITORY)
-- ============================================================

CREATE TABLE IF NOT EXISTS knowledge_base (
    tenant_id              UUID NOT NULL, -- FK removed for the demo script or ensure tenant exists
    id                     UUID NOT NULL DEFAULT gen_random_uuid(),
    
    language               VARCHAR(10) NOT NULL DEFAULT 'en',
    domain                 VARCHAR(50), 
    category               VARCHAR(50), 
    keyword                VARCHAR(255),
    
    content                TEXT NOT NULL,
    -- GENERATED ALWAYS content_hash: Prevents re-indexing the same text twice. 
    -- Saves massive IO during billion-row ingestion.
    content_hash           BYTEA GENERATED ALWAYS AS (digest(content, 'sha256')) STORED,
    source                 TEXT,
    
    -- metadata: Stores dynamic attributes (e.g., price_range, star_rating, season).
    metadata               JSONB DEFAULT '{}'::jsonb,
    
    -- embedding: halfvec(1536) cuts storage from 6TB to 3TB for 1B rows.
    embedding              halfvec(1536), 
    
    is_active              BOOLEAN DEFAULT TRUE,
    created_at             TIMESTAMPTZ DEFAULT NOW(),
    updated_at             TIMESTAMPTZ DEFAULT NOW(),

    PRIMARY KEY (tenant_id, id)
) PARTITION BY HASH (tenant_id);

-- DATABASE DOCUMENTATION
COMMENT ON TABLE knowledge_base IS 'Core RAG repository for AI Agent knowledge, partitioned for 1B row scale.';
COMMENT ON COLUMN knowledge_base.content_hash IS 'SHA256 hash for deduplication at scale.';
COMMENT ON COLUMN knowledge_base.embedding IS '16-bit float vector for high-performance semantic search.';
COMMENT ON COLUMN knowledge_base.metadata IS 'Schema-less attributes for domain-specific filtering (Travel, Finance, etc.).';

-- ============================================================
-- 23. Dynamic Configuration Block (Partitions & Vector Index)
-- ============================================================
DO $$
DECLARE
    c_num_partitions       CONSTANT INT := 8; -- e.g., 8 for Dev, 64-128 for Prod (999M rows)
    -- HNSW Index tuning (Higher = better recall but slower build/more RAM)
    c_hnsw_m               CONSTANT INT := 16;  -- Max connections per layer (typical: 16 to 64)
    c_hnsw_ef_construction CONSTANT INT := 64;  -- Size of dynamic list during build (typical: 64 to 256)
    i INT;
    v_sql TEXT;
BEGIN
    FOR i IN 0..(c_num_partitions - 1) LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS knowledge_base_p%s PARTITION OF knowledge_base FOR VALUES WITH (MODULUS %s, REMAINDER %s);',
            i, c_num_partitions, i
        );
    END LOOP;

    IF NOT EXISTS (SELECT 1 FROM pg_class c WHERE c.relname = 'idx_kb_embedding_hnsw') THEN
        EXECUTE format(
            'CREATE INDEX idx_kb_embedding_hnsw ON knowledge_base USING hnsw (embedding halfvec_cosine_ops) WITH (m = %s, ef_construction = %s);',
            c_hnsw_m, c_hnsw_ef_construction
        );
    END IF;
END $$;

-- ============================================================
-- 23 indexs for knowledge base
-- ============================================================
CREATE UNIQUE INDEX IF NOT EXISTS uniq_kb_tenant_hash ON knowledge_base (tenant_id, category, content_hash);
CREATE INDEX IF NOT EXISTS idx_kb_tenant_domain_lang ON knowledge_base (tenant_id, domain, language) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_kb_keyword ON knowledge_base (tenant_id, keyword);
CREATE INDEX IF NOT EXISTS idx_kb_metadata_gin ON knowledge_base USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_kb_content_fts ON knowledge_base USING GIN (to_tsvector('simple', content));

-- =========================
-- END OF SCHEMA.SQL
-- =========================