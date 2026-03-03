-- Processed transcripts: LLM-reflowed sentence chunks
--
-- Raw transcripts from Whisper are chunked on arbitrary buffer boundaries
-- (every 5 seconds).  This table stores the LLM post-processed version where
-- raw segments have been merged and reflowed into grammatically complete
-- sentences with corrected punctuation and casing.
--
-- Relationship to transcripts:
--   transcripts         — raw Whisper output, preserved verbatim
--   processed_transcripts — clean sentences derived from raw segments
--
-- speaker_id is populated by the same background attribution job that handles
-- the raw transcripts table (core/speaker_attribution.py).

CREATE TABLE IF NOT EXISTS processed_transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    speaker_id UUID REFERENCES speakers(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_processed_transcripts_meeting_id ON processed_transcripts(meeting_id);
CREATE INDEX idx_processed_transcripts_speaker_id ON processed_transcripts(speaker_id);
CREATE INDEX idx_processed_transcripts_time ON processed_transcripts(meeting_id, start_time);

-- Enable realtime so the UI receives processed sentences as they are produced
ALTER PUBLICATION supabase_realtime ADD TABLE processed_transcripts;
