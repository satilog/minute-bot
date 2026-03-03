-- Migrate voice embeddings from vector(256) to vector(512)
-- pyannote/embedding natively outputs 512-dimensional embeddings

-- =============================================================================
-- SPEAKERS TABLE
-- =============================================================================

DROP INDEX IF EXISTS idx_speakers_embedding;

ALTER TABLE speakers
    ALTER COLUMN voice_embedding TYPE vector(512);

CREATE INDEX idx_speakers_embedding ON speakers
    USING ivfflat (voice_embedding vector_cosine_ops) WITH (lists = 100);

-- =============================================================================
-- SPEAKER PROFILES TABLE
-- =============================================================================

DROP INDEX IF EXISTS idx_speaker_profiles_embedding;

ALTER TABLE speaker_profiles
    ALTER COLUMN voice_embedding TYPE vector(512);

CREATE INDEX idx_speaker_profiles_embedding ON speaker_profiles
    USING ivfflat (voice_embedding vector_cosine_ops) WITH (lists = 10);

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

CREATE OR REPLACE FUNCTION match_speakers(
    query_embedding vector(512),
    match_threshold FLOAT DEFAULT 0.8,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    meeting_id UUID,
    speaker_label TEXT,
    speaker_name TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id,
        s.meeting_id,
        s.speaker_label,
        s.speaker_name,
        1 - (s.voice_embedding <=> query_embedding) AS similarity
    FROM speakers s
    WHERE s.voice_embedding IS NOT NULL
    AND 1 - (s.voice_embedding <=> query_embedding) > match_threshold
    ORDER BY s.voice_embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

CREATE OR REPLACE FUNCTION match_speaker_profiles(
    query_embedding vector(512),
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
