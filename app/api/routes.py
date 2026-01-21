"""REST API endpoints."""
from fastapi import APIRouter, HTTPException, UploadFile, File
import os
import shutil
from app.services.rag_service import get_rag_service
from app.config import settings
from typing import Optional
import logging
import re

from app.models.schemas import QueryRequest, QueryResponse, NavigateRequest, NavigateResponse, RouteInfo, AssistRequest, AssistResponse, AssistAction
from app.core.agent import run_agent
from app.utils.helpers import generate_session_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai-agent", tags=["AI Agent"])


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Process a text-based query using the AI agent.
    
    This is the central dispatcher that determines the query intent
    and routes it to the appropriate logic.
    """
    try:
        logger.info(f"Received central query: {request.message[:100]}...")
        
        # Generate session ID if not provided
        session_id = request.session_id or generate_session_id()
        
        # Run the agent (the agent now returns a category)
        result = await run_agent(
            query=request.message, 
            session_id=session_id
        )
        category = result.get("category", "general")
        
        logger.info(f"Query categorized as: {category}")
        
        return QueryResponse(
            content=result["content"],
            category=category,
            tool_used=result["tool_used"],
            session_id=result["session_id"],
            target_route=result.get("target_route"),
            metadata=result.get("metadata", {})
        )
        
    except Exception as e:
        logger.error(f"Error in dispatcher: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process query: {str(e)}")


@router.post("/navigate", response_model=NavigateResponse)
async def navigate(request: NavigateRequest):
    """
    Process navigation commands directly.
    """
    try:
        logger.info(f"Received navigation command: {request.command}")
        
        # We can use the agent here as well for smarter parsing
        result = await run_agent(
            query=f"Internal Navigation Command: {request.command}. Current page: {request.context or 'unknown'}",
            session_id="nav_session"
        )
        
        target_route = result.get("target_route")
        if target_route:
            return NavigateResponse(
                targetRoute=target_route,
                action="navigate",
                message=result["content"]
            )
        else:
            return NavigateResponse(
                targetRoute="",
                action="none",
                message="I couldn't identify where you want to go. Please try saying 'take me to stats' or 'go to dashboard'."
            )
            
    except Exception as e:
        logger.error(f"Error in navigation endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Navigation failed: {str(e)}")


@router.get("/available-routes", response_model=list[RouteInfo])
async def get_available_routes():
    """
    Get all navigable routes with descriptions.
    """
    return [
        RouteInfo(name="Dashboard", path="#dashboard", description="Main overview of season progress and next matches"),
        RouteInfo(name="Players", path="#players", description="Player list, stats, and injury reports"),
        RouteInfo(name="Stats", path="#stats", description="Detailed tactical and team performance statistics"),
        RouteInfo(name="Settings", path="#settings", description="App configuration and user profile"),
        RouteInfo(name="Chat", path="#chat", description="Conversational AI assistant and file Q&A")
    ]


def _extract_quoted_text(command: str) -> Optional[str]:
    if not command:
        return None
    match = re.search(r'["“](.+?)["”]', command)
    if match:
        return match.group(1).strip()
    return None


def _detect_target_route(command: str) -> Optional[str]:
    if not command:
        return None
    text = command.lower()
    if "dashboard" in text or "لوحة" in text or "لوحة التحكم" in text:
        return "#dashboard"
    if "players" in text or "اللاعبين" in text:
        return "#players"
    if "stats" in text or "statistics" in text or "الإحصائيات" in text or "احصائيات" in text:
        return "#stats"
    if "settings" in text or "الإعدادات" in text or "الاعدادات" in text:
        return "#settings"
    if "chat" in text or "الدردشة" in text or "المحادثة" in text:
        return "#chat"
    return None


def _has_explicit_navigation_intent(command: str) -> bool:
    if not command:
        return False
    text = command.lower()
    return any(
        phrase in text
        for phrase in ["go to", "open", "take me to", "navigate to", "اذهب", "اذهب إلى", "افتح", "خذني إلى", "انتقل إلى"]
    )


@router.post("/assist", response_model=AssistResponse)
async def assist(request: AssistRequest):
    """
    Nav mic assistant endpoint: returns guided actions for UI automation.
    """
    try:
        command = (request.command or "").strip()
        command_lower = command.lower()
        actions: list[AssistAction] = []

        if not command:
            return AssistResponse(
                message="I didn't catch that. You can ask me to upload files, open chat, or guide you around the app.",
                actions=[],
                handled=False
            )

        if any(
            keyword in command_lower
            for keyword in ["guide", "help", "how do i", "how to", "show me around", "ارشاد", "إرشاد", "مساعدة", "كيف", "دلني"]
        ):
            actions.append(AssistAction(type="show_guide"))
            return AssistResponse(
                message=(
                    "Here’s a quick guide: use Chat to ask questions or learn from uploaded files, "
                    "use the Upload button in chat to add data, and use the sidebar to switch pages."
                ),
                actions=actions,
                handled=True
            )

        if _detect_target_route(command) and any(
            phrase in command_lower
            for phrase in [
                "don't take",
                "do not take",
                "don't go",
                "do not go",
                "don't navigate",
                "no navigation",
                "just explain",
                "only explain",
                "without going",
                "stay here",
                "don't open",
                "do not open",
                "لا تذهب",
                "لا تروح",
                "لا تنتقل",
                "فقط اشرح",
                "بس اشرح",
                "بدون ما تروح"
            ]
        ):
            return AssistResponse(
                message="",
                actions=[],
                handled=False
            )

        if any(keyword in command_lower for keyword in ["upload", "add file", "import", "ارفع", "رفع", "ملف", "استيراد"]):
            actions.append(AssistAction(type="open_chat"))
            actions.append(AssistAction(type="open_upload"))
            actions.append(AssistAction(type="highlight", target="uploadButton"))
            return AssistResponse(
                message="I opened the upload picker. Choose a file to add, then ask me about it in chat.",
                actions=actions,
                handled=True
            )

        if any(
            keyword in command_lower
            for keyword in ["learn from uploaded", "learn from files", "use uploaded files", "تعلم من الملفات", "استخدم الملفات", "من الملفات المرفوعة"]
        ):
            actions.append(AssistAction(type="open_chat"))
            actions.append(AssistAction(type="focus_chat_input"))
            actions.append(AssistAction(type="highlight", target="messageInput"))
            return AssistResponse(
                message="Go to Chat and ask about your uploaded documents, for example: 'Summarize the academy rules.'",
                actions=actions,
                handled=True
            )

        if any(keyword in command_lower for keyword in ["write", "type", "ask", "question", "اكتب", "اكتب لي", "اسأل", "سؤال"]):
            question = _extract_quoted_text(command)
            actions.append(AssistAction(type="open_chat"))
            actions.append(AssistAction(type="focus_chat_input"))
            if question:
                actions.append(AssistAction(type="insert_text", value=question))
                actions.append(AssistAction(type="highlight", target="messageInput"))
                return AssistResponse(
                    message="I've placed your question in the chat box. Say 'send it' if you want me to submit.",
                    actions=actions,
                    handled=True
                )

        if any(keyword in command_lower for keyword in ["send it", "send", "submit", "ارسل", "أرسل", "ارسله", "ارسال"]):
            actions.append(AssistAction(type="open_chat"))
            actions.append(AssistAction(type="send_text"))
            return AssistResponse(
                message="Sent. Let me know if you want to refine the question.",
                actions=actions,
                handled=True
            )

        target_route = _detect_target_route(command)
        if target_route and _has_explicit_navigation_intent(command):
            actions.append(AssistAction(type="navigate", value=target_route))
            return AssistResponse(
                message=f"I've taken you to {target_route.replace('#', '')}.",
                actions=actions,
                handled=True
            )

        return AssistResponse(
            message="I can upload files, open chat, type a question, send it, or guide you around the app. Try: 'upload a file' or 'show me around'.",
            actions=[],
            handled=False
        )

    except Exception as e:
        logger.error(f"Error in assist endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Assist failed: {str(e)}")


@router.post("/football-query", response_model=QueryResponse)
async def football_query(request: QueryRequest):
    """Legacy endpoint: now routes to central query dispatcher."""
    return await query(request)


@router.post("/training-advice", response_model=QueryResponse)
async def training_advice(request: QueryRequest):
    """Legacy endpoint: now routes to central query dispatcher."""
    return await query(request)


@router.post("/tactical-analysis", response_model=QueryResponse)
async def tactical_analysis(request: QueryRequest):
    """Legacy endpoint: now routes to central query dispatcher."""
    return await query(request)


@router.post("/context-aware-query", response_model=QueryResponse)
async def context_aware_query(request: QueryRequest):
    """Legacy endpoint: now routes to central query dispatcher."""
    return await query(request)


@router.post("/upload", response_model=dict)
async def upload_file(file: UploadFile = File(...)):
    """
    Upload and ingest a file (Excel or Text) into the RAG system.
    """
    try:
        # Create uploads directory if it doesn't exist
        os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
        
        file_path = os.path.join(settings.UPLOADS_DIR, file.filename)
        
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Clear RAG cache to ensure new data is picked up
        rag_service = get_rag_service()
        rag_service.clear_cache()
        
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in [".xlsx", ".xls", ".txt", ".md", ".pdf"]:
            return {"status": "error", "message": f"Unsupported file type: {file_ext}"}
            
        return {
            "status": "success",
            "filename": file.filename,
            "message": "File uploaded successfully"
        }
        
    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "ai-agent"}

