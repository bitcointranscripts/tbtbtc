import os.path

import pytest

from app.transcription import Transcription
from test_helpers import check_md_file


def rel_path(path):
    return os.path.relpath(
        os.path.abspath(os.path.join(os.path.dirname(__file__), path))
    )


@pytest.mark.feature
def test_audio_with_title():
    with open(rel_path("testAssets/transcript.txt"), "r") as file:
        result = file.read()
        file.close()
    source = rel_path("testAssets/audio.mp3")
    title = "title"
    username = "username"
    transcription = Transcription(
        test_mode=True,
    )
    transcription.add_transcription_source(source_file=source, title=title)
    transcripts = transcription.start()
    assert os.path.isfile(transcripts[0]["markdown"])
    check_md_file(
        path=transcripts[0]["markdown"],
        transcript_by=username,
        media=source,
        title=title,
        local=True,
    )
    transcription.clean_up()


@pytest.mark.feature
def test_audio_with_all_data():
    with open(rel_path("testAssets/transcript.txt"), "r") as file:
        result = file.read()
        file.close()
    source = rel_path("testAssets/audio.mp3")
    username = "username"
    title = "title"
    speakers = ["speaker1", "speaker2"]
    tags = ["tag1", "tag2"]
    category = "category"
    date = "2020-01-31"
    transcription = Transcription(
        test_mode=True,
    )
    transcription.add_transcription_source(
        source_file=source, title=title, date=date, tags=tags, category=category, speakers=speakers)
    transcripts = transcription.start()

    assert os.path.isfile(transcripts[0]["markdown"])
    check_md_file(
        path=transcripts[0]["markdown"],
        transcript_by=username,
        media=source,
        title=title,
        date=date,
        tags=tags,
        category=category,
        speakers=speakers,
        local=True,
    )
    transcription.clean_up()
