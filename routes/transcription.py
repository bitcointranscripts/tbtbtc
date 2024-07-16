import tempfile
import shutil
import os

from fastapi import APIRouter, Form, HTTPException, UploadFile, File, BackgroundTasks
from typing import Optional

from app.logging import get_logger
from app.transcription import Transcription
from app.types import GitHubMode

logger = get_logger()
router = APIRouter(tags=["Transcription"])

transcription_instance = None

def get_transcription_instance(**kwargs) -> Transcription:
    global transcription_instance
    if transcription_instance is None:
        transcription_instance = Transcription(**kwargs)
        logger.debug(transcription_instance)
    return transcription_instance

def reset_transcription_instance():
    global transcription_instance
    transcription_instance = None

@router.post("/preprocess/")
async def preprocess(
    loc: str = Form("misc"),
    title: Optional[str] = Form(None),
    date: Optional[str] = Form(None),
    tags: list[str] = Form([]),
    speakers: list[str] = Form([]),
    category: list[str] = Form([]),
    nocheck: bool = Form(False),
    cutoff_date: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    source_file: Optional[UploadFile] = File(None)
):
    try:
        logger.info(f"Preprocessing sources...")
        transcription = Transcription(
            queue=False,
            batch_preprocessing_output=True
        )

        if source_file:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                shutil.copyfileobj(source_file.file, tmp)
            transcription.add_transcription_source_JSON(tmp.name, nocheck=nocheck)
        else:
            transcription.add_transcription_source(
                source_file=source,
                loc=loc,
                title=title,
                date=date,
                tags=tags,
                category=category,
                speakers=speakers,
                preprocess=True,
                nocheck=nocheck,
                cutoff_date=cutoff_date
            )

        return {"status": "success", "data": [preprocessed_source for preprocessed_source in transcription.preprocessing_output]}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/add_to_queue/")
async def add_to_queue(
    loc: str = Form("misc"),
    model: str = Form("tiny.en"),
    title: Optional[str] = Form(None),
    date: Optional[str] = Form(None),
    tags: list[str] = Form([]),
    speakers: list[str] = Form([]),
    category: list[str] = Form([]),
    github: GitHubMode = Form("none"),
    deepgram: bool = Form(False),
    summarize: bool = Form(False),
    diarize: bool = Form(False),
    upload: bool = Form(False),
    model_output_dir: str = Form("local_models/"),
    nocleanup: bool = Form(False),
    noqueue: bool = Form(True),
    markdown: bool = Form(False),
    needs_review: bool = Form(False),
    nocheck: bool = Form(False),
    cutoff_date: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    source_file: Optional[UploadFile] = File(None)
):
    transcription = get_transcription_instance(
        model=model,
        github=github,
        summarize=summarize,
        deepgram=deepgram,
        diarize=diarize,
        upload=upload,
        model_output_dir=model_output_dir,
        nocleanup=nocleanup,
        queue=not noqueue,
        markdown=markdown,
        needs_review=needs_review
    )
    if source_file:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            shutil.copyfileobj(source_file.file, tmp)
            temp_file_path = tmp.name
        transcription.add_transcription_source_JSON(temp_file_path , nocheck=nocheck)
        os.remove(temp_file_path)
    else:
        transcription.add_transcription_source(
            source_file=source,
            loc=loc,
            title=title,
            date=date,
            tags=tags,
            category=category,
            speakers=speakers,
            nocheck=nocheck,
            cutoff_date=cutoff_date
        )

    return {"status": "queued", "message": "Transcription source has been added to the queue."}

@router.post("/remove_from_queue/")
async def remove_from_queue(
    source_file: UploadFile = File(...),
):
    if transcription_instance is None:
        return {"status": "error", "message": "No transcription instance available."}

    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            shutil.copyfileobj(source_file.file, tmp)
            temp_file_path = tmp.name

        removed_sources = transcription_instance.remove_transcription_source_JSON(temp_file_path)

        if not removed_sources:
            return {"status": "warning", "message": "No matching sources found in the queue to remove."}

        if not transcription_instance.transcripts:
            reset_transcription_instance()

        return {"status": "success", "message": f"Removed {len(removed_sources)} sources from the queue."}
    except Exception as e:
        logger.error(e)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@router.post("/start/")
async def start(background_tasks: BackgroundTasks):
    transcription = get_transcription_instance()
    
    if not transcription.transcripts:
        return {"status": "empty", "message": "No items in the transcription queue."}
    
    if transcription.status == "in_progress":
        return {"status": "in_progress", "message": "Transcription process is already running."}

    def run_and_reset_transcription():
        try:
            transcription.start()
        finally:
            reset_transcription_instance()

    background_tasks.add_task(run_and_reset_transcription)
    
    return {"status": "started", "message": "Transcription process has started."}

@router.get("/queue/")
async def get_queue():
    if transcription_instance is None:
        return {"data": []}

    queue = [
        {
            **transcript.source.to_json(),
        }
        for transcript in transcription_instance.transcripts
    ]
    return {"data": queue}
