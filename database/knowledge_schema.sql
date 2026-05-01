-- ============================================================
-- Extensions (safe)
-- ============================================================
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- for gen_random_uuid()

-- ============================================================
-- Table (safe)
-- ============================================================
CREATE TABLE IF NOT EXISTS travel_knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    destination TEXT,
    category TEXT, -- "info" | "cost"
    content TEXT,
    source TEXT,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- Indexes (safe)
-- ============================================================

-- Vector index (IVFFLAT)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c
        WHERE c.relname = 'idx_travel_knowledge_embedding'
    ) THEN
        CREATE INDEX idx_travel_knowledge_embedding
        ON travel_knowledge
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100);
    END IF;
END$$;

-- Destination index
CREATE INDEX IF NOT EXISTS idx_travel_destination
ON travel_knowledge(destination);

CREATE INDEX IF NOT EXISTS idx_travel_dest_cat
ON travel_knowledge(destination, category);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_travel_knowledge
ON travel_knowledge(destination, category, content);