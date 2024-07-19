import sys
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.config import settings
from app.data_fetcher import DataFetcher
from app.logging import get_logger
from app.types import TranscriptionCoverage

logger = get_logger()
router = APIRouter(tags=["Curator"])

try:
    data_fetcher = DataFetcher(base_url=settings.BTC_TRANSCRIPTS_URL)
except HTTPException as e:
    # Log the error and re-raise it
    logger.error(f"Failed to initialize server: {e.detail}")
    sys.exit(1)

class GetSourcesRequest(BaseModel):
    loc: str = 'all'
    coverage: Optional[TranscriptionCoverage] = 'none'

@router.post("/get_sources/")
async def get_sources(request: GetSourcesRequest):
    try:
        data = data_fetcher.get_sources(request.loc, request.coverage)
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/get_transcription_backlog/")
async def get_transcription_backlog():
    try:
        data = data_fetcher.get_transcription_backlog()
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=str(e))
