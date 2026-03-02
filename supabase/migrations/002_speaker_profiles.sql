-- Speaker Profiles
-- Global, meeting-independent voice identity store for cross-meeting speaker recognition

-- =============================================================================
-- SPEAKER PROFILES TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS speaker_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    voice_embedding vector(256) NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_speaker_profiles_name ON speaker_profiles(name);
CREATE INDEX idx_speaker_profiles_embedding ON speaker_profiles
    USING ivfflat (voice_embedding vector_cosine_ops) WITH (lists = 10);

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

-- Match against global speaker profiles by voice embedding similarity
CREATE OR REPLACE FUNCTION match_speaker_profiles(
    query_embedding vector(256),
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 1
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        sp.id,
        sp.name,
        1 - (sp.voice_embedding <=> query_embedding) AS similarity
    FROM speaker_profiles sp
    WHERE 1 - (sp.voice_embedding <=> query_embedding) > match_threshold
    ORDER BY sp.voice_embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Reuse the update_updated_at() function defined in migration 001
CREATE TRIGGER speaker_profiles_updated_at
    BEFORE UPDATE ON speaker_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
