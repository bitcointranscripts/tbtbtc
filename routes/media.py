from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.logging import get_logger
from app.media_processor import MediaProcessor

logger = get_logger()
router = APIRouter(tags=["Media"])

class VideoURLRequest(BaseModel):
    youtube_url: str

@router.post("/youtube-video-url")
async def youtube_video_url(request: VideoURLRequest):
    """Extract the direct video URL from a YouTube link"""
    try:
        processor = MediaProcessor()
        video_url = processor.get_youtube_video_url(request.youtube_url)
        if video_url:
            return {"status": "success", "video_url": video_url}
        else:
            error_msg = f"Failed to extract the video URL for {request.youtube_url}."
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        logger.error(f"Error extracting video URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))
