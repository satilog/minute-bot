"""Database operations for audio_files table and Supabase Storage."""

from typing import Optional

from supabase import Client

from minute_bot.db.client import STORAGE_BUCKET, get_supabase_client


class AudioFilesDB:
    """Database operations for audio_files table and Supabase Storage."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_supabase_client()
        self.table = "audio_files"
        self.bucket = STORAGE_BUCKET

    def create(
        self,
        meeting_id: str,
        file_path: str,
        duration_seconds: float,
        sample_rate: int = 16000,
    ) -> dict:
        """Create audio file record."""
        data = {
            "meeting_id": meeting_id,
            "file_path": file_path,
            "duration_seconds": duration_seconds,
            "sample_rate": sample_rate,
        }
        result = self.client.table(self.table).insert(data).execute()
        return result.data[0] if result.data else {}

    def upload_audio(
        self,
        meeting_id: str,
        audio_bytes: bytes,
        filename: str = "full_recording.wav",
    ) -> str:
        """Upload audio file to Supabase Storage."""
        file_path = f"{meeting_id}/{filename}"
        self.client.storage.from_(self.bucket).upload(
            file_path, audio_bytes, {"content-type": "audio/wav"}
        )
        return file_path

    def get_audio_url(self, file_path: str, expires_in: int = 3600) -> str:
        """Get signed URL for audio file."""
        result = self.client.storage.from_(self.bucket).create_signed_url(
            file_path, expires_in
        )
        return result.get("signedURL", "")

    def get_by_meeting(self, meeting_id: str) -> list[dict]:
        """Get audio files for a meeting."""
        result = (
            self.client.table(self.table)
            .select("*")
            .eq("meeting_id", meeting_id)
            .execute()
        )
        return result.data or []
