"""Tool definitions for the AI agent."""
from pydantic import BaseModel, Field
from typing import Annotated
from app.services.openai_service import get_openai_service
from app.services.rag_service import get_rag_service
import logging

logger = logging.getLogger(__name__)


class SearchInput(BaseModel):
    """Input schema for search tool."""
    query: Annotated[str, Field(description="The search query or question to search for on the internet")]


class SearchResult(BaseModel):
    """Output schema for search tool."""
    result: Annotated[str, Field(description="The search result or answer")]


class RAGInput(BaseModel):
    """Input schema for RAG tool."""
    query: Annotated[str, Field(description="The question to ask about the uploaded historical data or academy rules")]


class RAGResult(BaseModel):
    """Output schema for RAG tool."""
    result: Annotated[str, Field(description="The relevant information found in the local database")]


class NavigateInput(BaseModel):
    """Input schema for navigation tool."""
    target_page: Annotated[str, Field(description="The page name to navigate to (e.g., 'dashboard', 'players', 'stats', 'settings', 'chat')")]


class NavigateResult(BaseModel):
    """Output schema for navigation tool."""
    target_route: Annotated[str, Field(description="The actual anchor or URL for the page")]
    message: Annotated[str, Field(description="A confirmation message to the user")]


async def search_tool(query: SearchInput) -> SearchResult:
    # ... existing implementation ...
    try:
        logger.info(f"Executing search tool with query: {query.query}")
        openai_service = get_openai_service()
        result = openai_service.search(query.query)
        return SearchResult(result=result)
    except Exception as e:
        logger.error(f"Error in search_tool: {str(e)}", exc_info=True)
        return SearchResult(result=f"I encountered an error while searching: {str(e)}. Please try again.")


async def rag_tool(query: RAGInput) -> RAGResult:
    """
    Search local historical football data and academy rules.
    
    Use this tool when users ask about:
    - Academy specific rules and regulations
    - Historical data from uploaded Excel files
    - Internal documents or proprietary information
    
    Args:
        query: RAGInput containing the query string
        
    Returns:
        RAGResult containing the information found locally
    """
    try:
        logger.info(f"Executing RAG tool with query: {query.query}")
        rag_service = get_rag_service()
        result = rag_service.query(query.query)
        
        if not result:
            return RAGResult(result="I couldn't find any relevant information in the uploaded documents.")
            
        return RAGResult(result=result)
    except Exception as e:
        logger.error(f"Error in rag_tool: {str(e)}", exc_info=True)
        return RAGResult(result=f"I encountered an error while searching local documents: {str(e)}")


async def navigate_tool(input: NavigateInput) -> NavigateResult:
    """
    Navigate the user to a specific page or section of the web app.
    
    Use this tool when users say things like:
    - "Take me to the dashboard"
    - "Go to stats"
    - "Navigate to players page"
    - "Open settings"
    
    Args:
        input: NavigateInput containing the target_page
        
    Returns:
        NavigateResult containing the target_route and a confirmation message
    """
    try:
        target = input.target_page.lower().strip()
        logger.info(f"Executing navigate tool for target: {target}")
        
        # Simple mapping
        routes = {
            "dashboard": "#dashboard",
            "players": "#players",
            "settings": "#settings",
            "chat": "#chat"
        }
        
        route = routes.get(target)
        if route:
            return NavigateResult(
                target_route=route,
                message=f"Certainly! I'm taking you to the {target} page."
            )
        else:
            return NavigateResult(
                target_route="",
                message=f"I'm sorry, I don't recognize the '{target}' page. I can take you to Dashboard, Players, Stats, or Settings."
            )
            
    except Exception as e:
        logger.error(f"Error in navigate_tool: {str(e)}", exc_info=True)
        return NavigateResult(target_route="", message=f"I encountered an error while trying to navigate: {str(e)}")

