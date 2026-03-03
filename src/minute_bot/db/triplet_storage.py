"""Supabase Storage helpers for the triplet store.

Manages two private storage buckets:
  meeting-audio       — raw .wav / .mp3 audio files
  meeting-transcripts — parsed turn JSON and raw transcript text

File naming conventions:
  meeting-audio/{meeting_id}/{meeting_id}.Headset-0.wav
  meeting-transcripts/{meeting_id}/{meeting_id}_raw.txt
  meeting-transcripts/{meeting_id}/{meeting_id}_turns.json
  meeting-transcripts/{meeting_id}/{meeting_id}_extractions.json

Note: The main application's recording uploads (full_recording.wav) go to
the 'recordings' bucket via AudioFilesDB — that is a separate concern.
"""

from typing import Optional

from supabase import Client

from minute_bot.db.client import get_supabase_client


class TripletStorageDB:
    """Storage operations for the triplet store's audio and transcript buckets."""

    AUDIO_BUCKET = "meeting-audio"
    TRANSCRIPT_BUCKET = "meeting-transcripts"

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()

    def ensure_buckets(self) -> None:
        """Create the required storage buckets if they do not already exist.

        Both buckets are created as private. Safe to call multiple times.
        """
        existing = {b.name for b in self.client.storage.list_buckets()}
        for name in (self.AUDIO_BUCKET, self.TRANSCRIPT_BUCKET):
            if name not in existing:
                self.client.storage.create_bucket(name, options={"public": False})

    def upload_transcript(
        self,
        meeting_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Upload a file to the meeting-transcripts bucket.

        The object is stored at {meeting_id}/{filename}.

        Args:
            meeting_id:   Folder prefix.
            filename:     File name including extension.
            content:      Raw file bytes.
            content_type: MIME type (e.g. 'text/plain', 'application/json').

        Returns:
            Storage path string '{meeting_id}/{filename}'.
        """
        self.ensure_buckets()
        path = f"{meeting_id}/{filename}"
        self.client.storage.from_(self.TRANSCRIPT_BUCKET).upload(
            path,
            content,
            file_options={"content-type": content_type},
        )
        return path

    def upload_audio(self, meeting_id: str, filename: str, content: bytes) -> str:
        """Upload a file to the meeting-audio bucket.

        The object is stored at {meeting_id}/{filename}.

        Args:
            meeting_id: Folder prefix.
            filename:   File name including extension (e.g. '{meeting_id}.Headset-0.wav').
            content:    Raw audio bytes.

        Returns:
            Storage path string '{meeting_id}/{filename}'.
        """
        self.ensure_buckets()
        path = f"{meeting_id}/{filename}"
        self.client.storage.from_(self.AUDIO_BUCKET).upload(
            path,
            content,
            file_options={"content-type": "audio/wav"},
        )
        return path
