"""OpenAI API service for text responses and lightweight search-style answers."""
from typing import Optional
import logging
from openai import OpenAI
from app.config import settings
from app.core.prompts import SEARCH_TOOL_DESCRIPTION

logger = logging.getLogger(__name__)


class OpenAIService:
    """Service for interacting with OpenAI chat models."""

    def __init__(self):
        """Initialize OpenAI service with API key."""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables")

        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model_name = settings.OPENAI_MODEL
        logger.info(f"Initialized OpenAI service with model: {self.model_name}")

    def _chat(self, user_text: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_text})

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.7,
            top_p=0.8,
        )

        choice = response.choices[0].message.content if response.choices else ""
        return choice or "I'm sorry, I couldn't generate a response. Please try again."

    def search(self, query: str) -> str:
        """
        Provide a search-style response using the model's best available knowledge.

        Note: This does not perform live web search without additional tooling.
        """
        try:
            logger.info(f"Performing search-style response for: {query[:50]}...")
            return self._chat(query, system_prompt=SEARCH_TOOL_DESCRIPTION)
        except Exception as e:
            logger.error(f"Error in OpenAI search: {str(e)}", exc_info=True)
            raise Exception(f"Failed to search: {str(e)}")

    def generate_response(self, query: str, system_prompt: Optional[str] = None) -> str:
        """Generate a response using OpenAI with optional system prompt."""
        try:
            return self._chat(query, system_prompt=system_prompt)
        except Exception as e:
            logger.error(f"Error in OpenAI response generation: {str(e)}", exc_info=True)
            raise Exception(f"Failed to generate response: {str(e)}")


_openai_service_instance = None


def get_openai_service() -> OpenAIService:
    """Get or create OpenAI service instance (lazy initialization)."""
    global _openai_service_instance
    if _openai_service_instance is None:
        _openai_service_instance = OpenAIService()
    return _openai_service_instance

