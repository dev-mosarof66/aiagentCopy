"""Realtime API service for OpenAI streaming audio and text."""
import logging
import websockets
from app.config import settings

logger = logging.getLogger(__name__)


class LiveService:
    """Service for OpenAI Realtime API WebSocket sessions."""

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables")

        self.model = settings.OPENAI_REALTIME_MODEL
        self.url = f"wss://api.openai.com/v1/realtime?model={self.model}"
        logger.info(f"Realtime service initialized with model: {self.model}")

    def connect(self):
        """Create a websocket connection context manager to OpenAI Realtime."""
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }
        return websockets.connect(
            self.url, 
            additional_headers=headers,
            ping_interval=30,  # Increase interval
            ping_timeout=60    # Increase timeout for robustness during heavy CPU tasks
        )


# Global instance
_live_service_instance = None


def get_live_service() -> LiveService:
    """Get or create Live service instance (lazy initialization)."""
    global _live_service_instance
    if _live_service_instance is None:
        _live_service_instance = LiveService()
    return _live_service_instance

