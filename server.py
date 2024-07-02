import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.logging import configure_logger, get_logger
from app.media_processor import MediaProcessor

logger = get_logger()
app = FastAPI()

origins = [
    "http://localhost:3000",
    "https://staging-review.btctranscripts.com/",
    "https://review.btctranscripts.com/"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class VideoURLRequest(BaseModel):
    youtube_url: str

@app.post("/media/youtube-video-url")
async def youtube_video_url(request: VideoURLRequest):
    """Extract the direct video URL from a YouTube link"""
    try:
        configure_logger(log_level=logging.INFO)
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
