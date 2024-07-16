import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import config
from app.logging import configure_logger, get_logger
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

app.include_router(media_router, prefix="/media")
