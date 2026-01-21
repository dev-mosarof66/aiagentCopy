"""Configuration and environment settings."""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings."""
    
    def __init__(self):
        # API Keys
        self.OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
        
        # Model Configuration
        # Text/chat model used by the agent and tools
        self.OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        # Realtime model for streaming audio + text
        self.OPENAI_REALTIME_MODEL: str = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime")
        # Realtime voice for audio responses
        self.OPENAI_REALTIME_VOICE: str = os.getenv("OPENAI_REALTIME_VOICE", "alloy")
        # Audio formats for realtime input/output
        self.OPENAI_REALTIME_INPUT_FORMAT: str = os.getenv("OPENAI_REALTIME_INPUT_FORMAT", "pcm16")
        self.OPENAI_REALTIME_OUTPUT_FORMAT: str = os.getenv("OPENAI_REALTIME_OUTPUT_FORMAT", "pcm16")
        # Sample rate for PCM input (Hz)
        self.OPENAI_REALTIME_SAMPLE_RATE: int = int(os.getenv("OPENAI_REALTIME_SAMPLE_RATE", "24000"))
        
        # Server Configuration
        self.API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
        self.API_PORT: int = int(os.getenv("API_PORT", "8000"))
        self.DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
        
        # CORS Configuration
        cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000")
        self.CORS_ORIGINS: list = cors_origins_str.split(",") if cors_origins_str else []
        
        # Data Directories
        self.DATA_DIR: str = os.getenv("DATA_DIR", "data")
        self.UPLOADS_DIR: str = os.path.join(self.DATA_DIR, "uploads")


settings = Settings()

