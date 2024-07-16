import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import config
from app.exceptions import DuplicateSourceError
from app.logging import configure_logger, get_logger
from routes.curator import router as curator_router
from routes.transcription import router as transcription_router
from routes.media import router as media_router

logger = get_logger()
configure_logger(logging.DEBUG if config.getboolean('verbose_logging', False) else logging.INFO)
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

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.exception_handler(DuplicateSourceError)
async def duplicate_source_exception_handler(request, exc: DuplicateSourceError):
    return JSONResponse(
        status_code=409,
        content={"status": "warning", "message": str(exc)},
    )

app.include_router(transcription_router, prefix="/transcription")
app.include_router(curator_router, prefix="/curator")
app.include_router(media_router, prefix="/media")
