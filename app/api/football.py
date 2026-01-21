from fastapi import APIRouter, HTTPException, UploadFile, File
import os
import shutil
import uuid
from typing import Optional
import logging
from app.config import settings
from football_analysis.tracking_service import TrackingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/football", tags=["Football Analytics"])

# Initialize tracking service
tracking_service = TrackingService()

@router.post("/tracking")
async def track_video(file: UploadFile = File(...), match_key: str = "chelsea_man_city"):
    """
    Process a football video and return tracking data.
    """
    try:
        # Create temp directory if it doesn't exist
        temp_dir = os.path.join(settings.UPLOADS_DIR, "temp_tracking")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Ensure outputs dir exists
        outputs_dir = os.path.join(settings.DATA_DIR, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        
        # Save uploaded file to temp location
        file_ext = os.path.splitext(file.filename)[1]
        tracking_id = str(uuid.uuid4())
        temp_filename = f"{tracking_id}{file_ext}"
        temp_path = os.path.join(temp_dir, temp_filename)
        
        # Output video filename
        output_filename = f"annotated_{tracking_id}.mp4"
        output_path = os.path.join(outputs_dir, output_filename)
        
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        logger.info(f"Processing tracking for: {file.filename} as {match_key}")
        
        # Process video
        results = await tracking_service.process_video(temp_path, match_key=match_key, output_video_path=output_path)
        
        # Add video URL to results
        results["video_url"] = f"/outputs/{output_filename}"
        
        # Clean up temp file
        os.remove(temp_path)
        
        return results
        
    except Exception as e:
        logger.error(f"Error in tracking endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tracking failed: {str(e)}")
