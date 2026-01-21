"""Pydantic AI agent definition."""
import logging
from typing import Annotated, Literal
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings
from app.core.prompts import SYSTEM_PROMPT
from app.core.tools import search_tool, rag_tool, navigate_tool

logger = logging.getLogger(__name__)

class AgentResponse(BaseModel):
    """Structured response from the agent including classification."""
    content: str = Field(description="The detailed answer to the user's query")
    category: Literal["football", "tactical", "training", "general", "navigation"] = Field(
        description="The category of the query: 'football' (general knowledge), 'tactical' (formations/strategy), 'training' (methodology/drills), 'navigation' (app routing), or 'general' (chit-chat)"
    )

# Lazy agent initialization
_agent_instance = None


def get_agent() -> Agent:
    """Get or create agent instance (lazy initialization)."""
    global _agent_instance
    if _agent_instance is None:
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables")

        logger.info("Creating OpenAI provider for Pydantic AI")
        provider = OpenAIProvider(api_key=settings.OPENAI_API_KEY)

        model = OpenAIModel(
            model_name=settings.OPENAI_MODEL,
            provider=provider,
        )
        
        # Create agent with system prompt and tools
        _agent_instance = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=[search_tool, rag_tool, navigate_tool],
            output_type=AgentResponse,
        )
        
        logger.info(f"Pydantic AI agent initialized successfully with model: {settings.OPENAI_MODEL}")
    
    return _agent_instance


async def run_agent(query: str, session_id: str = None) -> dict:
    """
    Run the agent with a user query.
    
    Args:
        query: User's query message
        session_id: Optional session ID for conversation context
        
    Returns:
        Dictionary with response content and metadata
    """
    try:
        logger.info(f"Running agent with query: {query[:100]}...")
        
        # Get agent instance
        agent = get_agent()
        
        # Run the agent
        result = await agent.run(query)
        
        # Extract response
        response_obj = result.output
        response_text = response_obj.content
        category = response_obj.category
        messages = result.all_messages()
        
        # Determine which tool was used
        tool_used = "general"
        target_route = None
        
        # Check if any tools were called
        if messages:
            for msg in messages:
                if hasattr(msg, 'parts'):
                    for part in msg.parts:
                        if hasattr(part, 'tool_name'):
                            if part.tool_name == "search_tool":
                                tool_used = "search"
                                break
                            elif part.tool_name == "rag_tool":
                                tool_used = "rag"
                                break
                            elif part.tool_name == "navigate_tool":
                                tool_used = "navigation"
                                # If it's navigation, we need to extract the target_route from tool outputs
                                # Since we're in a simple setup, we'll try to find the NavigateResult
                                break
            
            # Extract tool result if navigation was used
            if tool_used == "navigation":
                for msg in messages:
                    if hasattr(msg, 'parts'):
                        for part in msg.parts:
                            if hasattr(part, 'content') and 'target_route' in str(part.content):
                                try:
                                    import json
                                    # Very naive extraction of the JSON from the tool result string
                                    content_str = str(part.content)
                                    # Tool results in pydantic-ai are often formatted string representations
                                    if "#dashboard" in content_str: target_route = "#dashboard"
                                    elif "#players" in content_str: target_route = "#players"
                                    elif "#stats" in content_str: target_route = "#stats"
                                    elif "#settings" in content_str: target_route = "#settings"
                                    elif "#chat" in content_str: target_route = "#chat"
                                except:
                                    pass
        
        return {
            "content": response_text,
            "category": category,
            "tool_used": tool_used,
            "session_id": session_id,
            "target_route": target_route,
            "metadata": {
                "model": settings.OPENAI_MODEL,
                "category": category
            }
        }
        
    except Exception as e:
        logger.error(f"Error running agent: {str(e)}", exc_info=True)
        raise Exception(f"Failed to process query: {str(e)}")

