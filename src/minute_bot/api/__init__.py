"""Flask API layer for Minute Bot."""

import atexit
import logging

from apiflask import APIFlask

from minute_bot.config import get_settings


def create_app() -> APIFlask:
    """Application factory for creating Flask app."""
    app = APIFlask(
        __name__,
        title="Minute Bot API",
        version="1.0.0",
        docs_ui="swagger-ui",
    )
    app.config["SPEC_FORMAT"] = "json"
    app.info = {
        "description": (
            "Agentic meeting memory system. Captures audio, transcribes speech, "
            "diarizes speakers, and builds a queryable knowledge graph per meeting."
        ),
    }
    app.tags = [
        {"name": "meetings", "description": "Primary workflow: start, stream, and stop recordings"},
        {"name": "profiles", "description": "Global speaker profile enrollment and management"},
        {"name": "transcription", "description": "Transcription pipeline status and direct transcription"},
        {"name": "diarization", "description": "Speaker diarization pipeline status"},
        {"name": "streaming", "description": "Audio pipeline diagnostics"},
        {"name": "health", "description": "Server and model health"},
    ]

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Register blueprints
    from minute_bot.api import diarization, health, meetings, profiles, streaming, transcription

    app.register_blueprint(health.bp)
    app.register_blueprint(streaming.bp)
    app.register_blueprint(transcription.bp)
    app.register_blueprint(diarization.bp)
    app.register_blueprint(meetings.bp)
    app.register_blueprint(profiles.bp)

    # Initialize shared services (ML models load in background threads)
    from minute_bot.services import registry

    registry.initialize()

    # Auto-start pub/sub processing pipelines
    transcription._init_processing()
    diarization._init_processing()

    # Cleanup on shutdown
    @atexit.register
    def cleanup():
        from minute_bot.api import transcription, diarization

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
