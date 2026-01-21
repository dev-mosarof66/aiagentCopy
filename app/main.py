"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import logging
import os

from app.config import settings
from app.api import routes, websocket, football
from app.utils.helpers import ensure_directory

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Ensure data directories exist
ensure_directory(settings.DATA_DIR)
ensure_directory(settings.UPLOADS_DIR)

# Create FastAPI app
app = FastAPI(
    title="CoachHub AI Agent API",
    description="AI Agent for Elite Football Analytics",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(routes.router)
app.include_router(websocket.router)
app.include_router(football.router)

# Serve outputs
outputs_dir = os.path.join(settings.DATA_DIR, "outputs")
os.makedirs(outputs_dir, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=outputs_dir), name="outputs")

# Serve frontend files if they exist
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "CoachHub AI Agent API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting CoachHub AI Agent API...")
    logger.info(f"Model: {settings.OPENAI_MODEL}")
    logger.info(f"API Key configured: {'Yes' if settings.OPENAI_API_KEY else 'No'}")
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY is not set! Please set it in .env file")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down CoachHub AI Agent API...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )

