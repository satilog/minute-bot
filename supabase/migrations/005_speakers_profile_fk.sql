-- Link speakers (per-meeting) back to the matched speaker_profile (global identity)
--
-- When diarization matches a speaker's voice embedding against speaker_profiles,
-- we now store the profile FK so the relationship is explicit and queryable.
-- NULL means the speaker was not matched to any enrolled profile (anonymous).

ALTER TABLE speakers
    ADD COLUMN IF NOT EXISTS profile_id UUID
        REFERENCES speaker_profiles(id) ON DELETE SET NULL;

CREATE INDEX idx_speakers_profile_id ON speakers(profile_id);
