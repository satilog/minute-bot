-- Migration 003: Add graph_processing_status to meetings
-- Tracks the status of the manual "Process Transcript" step which runs LLM
-- transcript cleanup and knowledge-graph extraction after a meeting ends.
-- Values: NULL (not started) | 'pending' | 'processing' | 'completed' | 'failed'

ALTER TABLE meetings ADD COLUMN IF NOT EXISTS graph_processing_status TEXT;
