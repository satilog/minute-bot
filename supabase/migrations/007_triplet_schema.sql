-- Migration: 007_triplet_schema
-- Description: Initial schema for meeting memory triplet store
-- Safe to re-run: yes (all statements are idempotent)
-- Run this in: Supabase SQL Editor

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

-- Core triplet store: subject-predicate-object facts with temporal validity
-- and vector embeddings for semantic search.
CREATE TABLE IF NOT EXISTS triplets (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subject_text        TEXT NOT NULL,
    subject_type        TEXT NOT NULL,
    subject_id          TEXT NOT NULL,
    predicate           TEXT NOT NULL,
    object_text         TEXT NOT NULL,
    object_type         TEXT NOT NULL,
    object_id           TEXT NOT NULL,
    full_text           TEXT NOT NULL,
    source_turn_id      TEXT NOT NULL,
    source_meeting_id   TEXT NOT NULL,
    sequence            INTEGER NOT NULL,
    speaker_id          TEXT NOT NULL,
    event_type          TEXT,
    confidence          FLOAT DEFAULT 1.0,
    valid_from          INTEGER NOT NULL,
    valid_until         INTEGER,
    embedding           VECTOR(1536),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Directed links between triplets (subject_match, object_match, subject_object)
CREATE TABLE IF NOT EXISTS triplet_links (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_id     UUID REFERENCES triplets(id) ON DELETE CASCADE,
    to_id       UUID REFERENCES triplets(id) ON DELETE CASCADE,
    link_type   TEXT NOT NULL,
    weight      FLOAT DEFAULT 1.0,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (from_id, to_id, link_type)
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_triplets_subject_id  ON triplets (subject_id);
CREATE INDEX IF NOT EXISTS idx_triplets_object_id   ON triplets (object_id);
CREATE INDEX IF NOT EXISTS idx_triplets_predicate   ON triplets (predicate);
CREATE INDEX IF NOT EXISTS idx_triplets_valid_range ON triplets (valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_triplets_meeting_seq ON triplets (source_meeting_id, sequence);
CREATE INDEX IF NOT EXISTS idx_triplets_event_type  ON triplets (event_type);
CREATE INDEX IF NOT EXISTS idx_links_from_id        ON triplet_links (from_id);
CREATE INDEX IF NOT EXISTS idx_links_to_id          ON triplet_links (to_id);
CREATE INDEX IF NOT EXISTS idx_links_type           ON triplet_links (link_type);

-- HNSW index for fast approximate nearest-neighbour search on embeddings.
CREATE INDEX IF NOT EXISTS idx_triplets_embedding ON triplets
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- RPC Functions
-- ---------------------------------------------------------------------------

-- Semantic vector search over triplets.
CREATE OR REPLACE FUNCTION search_triplets(
    query_embedding VECTOR(1536),
    match_threshold FLOAT DEFAULT 0.78,
    match_count     INT DEFAULT 10
)
RETURNS TABLE (
    id                UUID,
    subject_id        TEXT,
    predicate         TEXT,
    object_id         TEXT,
    full_text         TEXT,
    source_meeting_id TEXT,
    sequence          INT,
    speaker_id        TEXT,
    event_type        TEXT,
    confidence        FLOAT,
    valid_from        INT,
    valid_until       INT,
    similarity        FLOAT
)
LANGUAGE sql STABLE AS $$
    SELECT
        t.id, t.subject_id, t.predicate, t.object_id,
        t.full_text, t.source_meeting_id, t.sequence,
        t.speaker_id, t.event_type, t.confidence,
        t.valid_from, t.valid_until,
        1 - (t.embedding <=> query_embedding) AS similarity
    FROM triplets t
    WHERE 1 - (t.embedding <=> query_embedding) > match_threshold
    ORDER BY t.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Graph state at a given sequence point within a meeting.
CREATE OR REPLACE FUNCTION get_snapshot(
    p_meeting_id TEXT,
    p_sequence   INT
)
RETURNS SETOF triplets
LANGUAGE sql STABLE AS $$
    SELECT * FROM triplets
    WHERE source_meeting_id = p_meeting_id
      AND valid_from  <= p_sequence
      AND (valid_until IS NULL OR valid_until > p_sequence)
    ORDER BY sequence;
$$;

-- All triplets that reference a given entity (as subject or object).
CREATE OR REPLACE FUNCTION get_entity_context(p_entity_id TEXT)
RETURNS SETOF triplets
LANGUAGE sql STABLE AS $$
    SELECT * FROM triplets
    WHERE subject_id = p_entity_id
       OR object_id  = p_entity_id
    ORDER BY source_meeting_id, sequence;
$$;

-- All active task assignments (predicate = assigned_to, still open).
CREATE OR REPLACE FUNCTION get_open_tasks()
RETURNS SETOF triplets
LANGUAGE sql STABLE AS $$
    SELECT * FROM triplets
    WHERE predicate   = 'assigned_to'
      AND valid_until IS NULL
    ORDER BY sequence DESC;
$$;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

ALTER TABLE triplets      ENABLE ROW LEVEL SECURITY;
ALTER TABLE triplet_links ENABLE ROW LEVEL SECURITY;

-- Create read policy only if it does not already exist.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename  = 'triplets'
          AND policyname = 'allow_read_triplets'
    ) THEN
        EXECUTE 'CREATE POLICY "allow_read_triplets" ON triplets
                 FOR SELECT TO authenticated USING (true)';
    END IF;
END $$;
