-- Minute Bot Database Schema
-- Initial migration: Core tables for meeting memory system

-- Enable pgvector extension for voice embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- MEETINGS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT UNIQUE NOT NULL,
    title TEXT,
    start_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    end_time TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'failed')),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_meetings_session_id ON meetings(session_id);
CREATE INDEX idx_meetings_status ON meetings(status);
CREATE INDEX idx_meetings_start_time ON meetings(start_time DESC);

-- =============================================================================
-- AUDIO FILES TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS audio_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    duration_seconds FLOAT,
    sample_rate INTEGER DEFAULT 16000,
    channels INTEGER DEFAULT 1,
    format TEXT DEFAULT 'wav',
    file_size_bytes BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audio_files_meeting_id ON audio_files(meeting_id);

-- =============================================================================
-- SPEAKERS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS speakers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker_label TEXT NOT NULL,
    speaker_name TEXT,
    voice_embedding vector(256),  -- Pyannote embedding dimension
    total_speaking_time FLOAT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(meeting_id, speaker_label)
);

CREATE INDEX idx_speakers_meeting_id ON speakers(meeting_id);
CREATE INDEX idx_speakers_embedding ON speakers USING ivfflat (voice_embedding vector_cosine_ops) WITH (lists = 100);

-- =============================================================================
-- TRANSCRIPTS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker_id UUID REFERENCES speakers(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    language TEXT DEFAULT 'en',
    words JSONB DEFAULT '[]',  -- Word-level timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_transcripts_meeting_id ON transcripts(meeting_id);
CREATE INDEX idx_transcripts_speaker_id ON transcripts(speaker_id);
CREATE INDEX idx_transcripts_time ON transcripts(meeting_id, start_time);

-- =============================================================================
-- EVENTS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker_id UUID REFERENCES speakers(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    timestamp FLOAT NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source_text TEXT,
    requires_action BOOLEAN DEFAULT FALSE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_meeting_id ON events(meeting_id);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_speaker_id ON events(speaker_id);
CREATE INDEX idx_events_time ON events(meeting_id, timestamp);

-- =============================================================================
-- ENTITIES TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(meeting_id, entity_type, entity_name)
);

CREATE INDEX idx_entities_meeting_id ON entities(meeting_id);
CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_name ON entities(entity_name);

-- =============================================================================
-- RELATIONSHIPS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    source_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    timestamp FLOAT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_relationships_meeting_id ON relationships(meeting_id);
CREATE INDEX idx_relationships_source ON relationships(source_entity_id);
CREATE INDEX idx_relationships_target ON relationships(target_entity_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type);

-- =============================================================================
-- ENTITY MENTIONS TABLE
-- =============================================================================
CREATE TABLE IF NOT EXISTS entity_mentions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    transcript_id UUID REFERENCES transcripts(id) ON DELETE CASCADE,
    event_id UUID REFERENCES events(id) ON DELETE CASCADE,
    mention_text TEXT,
    context TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_entity_mentions_entity_id ON entity_mentions(entity_id);
CREATE INDEX idx_entity_mentions_transcript_id ON entity_mentions(transcript_id);
CREATE INDEX idx_entity_mentions_event_id ON entity_mentions(event_id);

-- =============================================================================
-- GRAPH SNAPSHOTS TABLE (for temporal queries)
-- =============================================================================
CREATE TABLE IF NOT EXISTS graph_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    snapshot_time FLOAT NOT NULL,
    snapshot_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_graph_snapshots_meeting_id ON graph_snapshots(meeting_id);
CREATE INDEX idx_graph_snapshots_time ON graph_snapshots(meeting_id, snapshot_time);

-- =============================================================================
-- FUNCTIONS
-- =============================================================================

-- Function to match speakers by voice embedding similarity
CREATE OR REPLACE FUNCTION match_speakers(
    query_embedding vector(256),
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

-- Function to update timestamps on row update
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers
CREATE TRIGGER meetings_updated_at
    BEFORE UPDATE ON meetings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER speakers_updated_at
    BEFORE UPDATE ON speakers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- ROW LEVEL SECURITY (optional, for multi-tenant setup)
-- =============================================================================

-- Enable RLS on all tables (policies would need to be added based on auth requirements)
-- ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE audio_files ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE speakers ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE transcripts ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE events ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE entities ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE relationships ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE entity_mentions ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE graph_snapshots ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- REALTIME SUBSCRIPTIONS
-- =============================================================================

-- Enable realtime for frontend subscriptions
ALTER PUBLICATION supabase_realtime ADD TABLE transcripts;
ALTER PUBLICATION supabase_realtime ADD TABLE speakers;
ALTER PUBLICATION supabase_realtime ADD TABLE events;
ALTER PUBLICATION supabase_realtime ADD TABLE entities;
ALTER PUBLICATION supabase_realtime ADD TABLE relationships;
