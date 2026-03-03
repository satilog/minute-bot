-- Add speaker_attribution_status to meetings table
--
-- After a meeting recording ends, a background post-processing step matches
-- each transcript chunk to a diarized speaker by time overlap and writes the
-- speaker_id onto the transcript row.  This column tracks that process so the
-- UI can show an appropriate loading / done indicator.
--
-- Lifecycle:
--   pending    → meeting just stopped, attribution not yet started
--   processing → attribution job is running in the background
--   completed  → all transcripts have been attributed to speakers
--   failed     → attribution job encountered an unrecoverable error
--
-- The UI should poll GET /meetings/<id> and inspect this field to decide
-- whether to show a "processing speakers…" spinner or a final speaker breakdown.

ALTER TABLE meetings
    ADD COLUMN IF NOT EXISTS speaker_attribution_status TEXT
        NOT NULL DEFAULT 'pending'
        CHECK (speaker_attribution_status IN ('pending', 'processing', 'completed', 'failed'));

CREATE INDEX idx_meetings_attribution_status
    ON meetings(speaker_attribution_status);
