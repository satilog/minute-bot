"""Flask API layer for Minute Bot."""

import atexit
import logging

from flask import Flask

from minute_bot.config import get_settings


def create_app() -> Flask:
    """Application factory for creating Flask app."""
    app = Flask(__name__)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Register blueprints
    from minute_bot.api import diarization, health, meetings, streaming, transcription

    app.register_blueprint(health.bp)
    app.register_blueprint(streaming.bp)
    app.register_blueprint(transcription.bp)
    app.register_blueprint(diarization.bp)
    app.register_blueprint(meetings.bp)

    # Cleanup on shutdown
    @atexit.register
    def cleanup():
        """Cleanup resources on shutdown."""
        from minute_bot.api import streaming, transcription, diarization

        if streaming._audio_capture and streaming._audio_capture.is_running:
            streaming._audio_capture.stop()

        if transcription._subscriber:
            transcription._subscriber.stop()

        if diarization._subscriber:
            diarization._subscriber.stop()

    return app


def main():
    """Main entry point for running the application."""
    settings = get_settings()
    app = create_app()

    app.run(
        host="0.0.0.0",
        port=settings.port,
        debug=settings.debug,
    )


if __name__ == "__main__":
    main()
