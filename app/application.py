"""This module provides the transcript cli."""
import errno
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import boto3
import pytube
import requests
import static_ffmpeg
import whisper
import yt_dlp
from clint.textui import progress
from deepgram import Deepgram
from dotenv import dotenv_values
from moviepy.editor import VideoFileClip
from pytube.exceptions import PytubeError

from app import __app_name__, __version__


def download_video(url, working_dir="tmp/"):
    logger = logging.getLogger(__app_name__)
    try:
        logger.info("URL: " + url)
        logger.info("Downloading video... Please wait.")

        ydl_opts = {
            "format": "18",
            "outtmpl": os.path.join(working_dir, "videoFile.%(ext)s"),
            "nopart": True,
            "writeinfojson": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ytdl:
            ytdl.download([url])

        with open(os.path.join(working_dir, "videoFile.info.json")) as file:
            info = ytdl.sanitize_info(json.load(file))
            name = info["title"].replace("/", "-")
            file.close()

        os.rename(
            os.path.join(working_dir, "videoFile.mp4"),
            os.path.join(working_dir, name + ".mp4"),
        )

        return os.path.abspath(os.path.join(working_dir, name + ".mp4"))
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        shutil.rmtree(working_dir)
        return


def read_description(prefix):
    logger = logging.getLogger(__app_name__)
    try:
        list_of_chapters = []
        with open(prefix + "videoFile.info.json", "r") as f:
            info = json.load(f)
        if "chapters" not in info:
            logger.info("No chapters found in description")
            return list_of_chapters
        for index, x in enumerate(info["chapters"]):
            name = x["title"]
            start = x["start_time"]
            list_of_chapters.append((str(index), start, str(name)))

        return list_of_chapters
    except Exception as e:
        logger.error(f"Error reading description: {e}")
        return []


def write_chapters_file(chapter_file: str, chapter_list: list) -> None:
    # Write out the chapter file based on simple MP4 format (OGM)
    logger = logging.getLogger(__app_name__)
    try:
        with open(chapter_file, "w") as fo:
            for current_chapter in chapter_list:
                fo.write(
                    f"CHAPTER{current_chapter[0]}="
                    f"{current_chapter[1]}\n"
                    f"CHAPTER{current_chapter[0]}NAME="
                    f"{current_chapter[2]}\n"
                )
            fo.close()
    except Exception as e:
        logger.error("Error writing chapter file")
        logger.error(e)


def convert_video_to_mp3(filename, working_dir="tmp/"):
    logger = logging.getLogger(__app_name__)
    try:
        clip = VideoFileClip(filename)
        logger.info("Converting video to mp3... Please wait.")
        logger.info(filename[:-4] + ".mp3")
        clip.audio.write_audiofile(
            os.path.join(working_dir, filename.split("/")[-1][:-4] + ".mp3")
        )
        clip.close()
        logger.info("Converted video to mp3")
        return os.path.join(working_dir, filename.split("/")[-1][:-4] + ".mp3")
    except Exception as e:
        logger.error(f"Error converting video to mp3: {e}")
        return None


def convert_wav_to_mp3(abs_path, filename, working_dir="tmp/"):
    logger = logging.getLogger(__app_name__)
    op = subprocess.run(
        ["ffmpeg", "-i", abs_path, filename[:-4] + ".mp3"],
        cwd=working_dir,
        capture_output=True,
        text=True,
    )
    logger.info(op.stdout)
    logger.error(op.stderr)
    return os.path.abspath(os.path.join(working_dir, filename[:-4] + ".mp3"))


def check_if_playlist(media):
    logger = logging.getLogger(__app_name__)
    try:
        if (
            media.startswith("PL")
            or media.startswith("UU")
            or media.startswith("FL")
            or media.startswith("RD")
        ):
            return True
        playlists = list(pytube.Playlist(media).video_urls)
        if type(playlists) is not list:
            return False
        return True
    except Exception as e:
        logger.error(f"Pytube Error: {e}")
        return False


def check_if_video(media):
    logger = logging.getLogger(__app_name__)
    if re.search(r"^([\dA-Za-z_-]{11})$", media):
        return True
    try:
        pytube.YouTube(media)
        return True
    except PytubeError as e:
        logger.error(f"Pytube Error: {e}")
        return False


def get_playlist_videos(url):
    logger = logging.getLogger(__app_name__)
    try:
        videos = pytube.Playlist(url)
        return videos
    except Exception as e:
        logger.error("Error getting playlist videos")
        logger.error(e)
        return


def get_audio_file(url, title, working_dir="tmp/"):
    logger = logging.getLogger(__app_name__)
    logger.info("URL: " + url)
    logger.info("downloading audio file")
    try:
        audio = requests.get(url, stream=True)
        with open(os.path.join(working_dir, title + ".mp3"), "wb") as f:
            total_length = int(audio.headers.get("content-length"))
            for chunk in progress.bar(
                audio.iter_content(chunk_size=1024),
                expected_size=(total_length / 1024) + 1,
            ):
                if chunk:
                    f.write(chunk)
                    f.flush()
        return os.path.join(working_dir, title + ".mp3")
    except Exception as e:
        logger.error("Error downloading audio file")
        logger.error(e)
        return


def process_mp3(filename, model, upload, model_output_dir):
    logger = logging.getLogger(__app_name__)
    logger.info("Transcribing audio to text using whisper ...")
    try:
        my_model = whisper.load_model(model)
        result = my_model.transcribe(filename)
        data = []
        for x in result["segments"]:
            data.append(tuple((x["start"], x["end"], x["text"])))
        data_path = generate_srt(data, filename, model_output_dir)
        if upload:
            upload_file_to_s3(data_path)
        logger.info("Removed video and audio files")
        return data
    except Exception as e:
        logger.error("Error transcribing audio to text")
        logger.error(e)
        return


def decimal_to_sexagesimal(dec):
    sec = int(dec % 60)
    minu = int((dec // 60) % 60)
    hrs = int((dec // 60) // 60)

    return f"{hrs:02d}:{minu:02d}:{sec:02d}"


def combine_chapter(chapters, transcript, working_dir="tmp/"):
    logger = logging.getLogger(__app_name__)
    try:
        chapters_pointer = 0
        transcript_pointer = 0
        result = ""
        # chapters index, start time, name
        # transcript start time, end time, text

        while chapters_pointer < len(chapters) and transcript_pointer < len(
            transcript
        ):
            if (
                chapters[chapters_pointer][1]
                <= transcript[transcript_pointer][0]
            ):
                result = (
                    result + "\n\n## " + chapters[chapters_pointer][2] + "\n\n"
                )
                chapters_pointer += 1
            else:
                result = result + transcript[transcript_pointer][2]
                transcript_pointer += 1

        while transcript_pointer < len(transcript):
            result = result + transcript[transcript_pointer][2]
            transcript_pointer += 1

        return result
    except Exception as e:
        logger.error("Error combining chapters")
        logger.error(e)


def combine_deepgram_chapters_with_diarization(deepgram_data, chapters):
    logger = logging.getLogger(__app_name__)
    try:
        para = ""
        string = ""
        curr_speaker = None
        words = deepgram_data["results"]["channels"][0]["alternatives"][0][
            "words"
        ]
        words_pointer = 0
        chapters_pointer = 0
        while chapters_pointer < len(chapters) and words_pointer < len(words):
            if chapters[chapters_pointer][1] <= words[words_pointer]["start"]:
                if para != "":
                    para = para.strip(" ")
                    string = string + para + "\n\n"
                para = ""
                string = string + f"## {chapters[chapters_pointer][2]}\n\n"
                chapters_pointer += 1
            else:
                if words[words_pointer]["speaker"] != curr_speaker:
                    if para != "":
                        para = para.strip(" ")
                        string = string + para + "\n\n"
                    para = ""
                    string = (
                        string
                        + f'Speaker {words[words_pointer]["speaker"]}: '
                        + decimal_to_sexagesimal(words[words_pointer]["start"])
                    )
                    curr_speaker = words[words_pointer]["speaker"]
                    string = string + "\n\n"

                para = para + " " + words[words_pointer]["punctuated_word"]
                words_pointer += 1
        while words_pointer < len(words):
            if words[words_pointer]["speaker"] != curr_speaker:
                if para != "":
                    para = para.strip(" ")
                    string = string + para + "\n\n"
                para = ""
                string = (
                    string + f'Speaker {words[words_pointer]["speaker"]}:'
                    f' {decimal_to_sexagesimal(words[words_pointer]["start"])}'
                )
                curr_speaker = words[words_pointer]["speaker"]
                string = string + "\n\n"

            para = para + " " + words[words_pointer]["punctuated_word"]
            words_pointer += 1
        para = para.strip(" ")
        string = string + para
        return string
    except Exception as e:
        logger.error("Error combining deepgram chapters")
        logger.error(e)


def get_deepgram_transcript(
    deepgram_data, diarize, title, upload, model_output_dir
):
    if diarize:
        para = ""
        string = ""
        curr_speaker = None
        data_path = save_local_json(deepgram_data, title, model_output_dir)
        if upload:
            upload_file_to_s3(data_path)
        for word in deepgram_data["results"]["channels"][0]["alternatives"][0][
            "words"
        ]:
            if word["speaker"] != curr_speaker:
                if para != "":
                    para = para.strip(" ")
                    string = string + para + "\n\n"
                para = ""
                string = (
                    string + f'Speaker {word["speaker"]}: '
                    f'{decimal_to_sexagesimal(word["start"])}'
                )
                curr_speaker = word["speaker"]
                string = string + "\n\n"

            para = para + " " + word["punctuated_word"]
        para = para.strip(" ")
        string = string + para
        return string
    else:
        data_path = save_local_json(deepgram_data, title, model_output_dir)
        if upload:
            upload_file_to_s3(data_path)
        return deepgram_data["results"]["channels"][0]["alternatives"][0][
            "transcript"
        ]


def get_deepgram_summary(deepgram_data):
    logger = logging.getLogger(__app_name__)
    try:
        summaries = deepgram_data["results"]["channels"][0]["alternatives"][0][
            "summaries"
        ]
        summary = ""
        for x in summaries:
            summary = summary + " " + x["summary"]
        return summary.strip(" ")
    except Exception as e:
        logger.error("Error getting summary")
        logger.error(e)


def process_mp3_deepgram(filename, summarize, diarize):
    logger = logging.getLogger(__app_name__)
    logger.info("Transcribing audio to text using deepgram...")
    try:
        config = dotenv_values(".env")
        dg_client = Deepgram(config["DEEPGRAM_API_KEY"])

        with open(filename, "rb") as audio:
            mimeType = mimetypes.MimeTypes().guess_type(filename)[0]
            source = {"buffer": audio, "mimetype": mimeType}
            response = dg_client.transcription.sync_prerecorded(
                source,
                {
                    "punctuate": True,
                    "speaker_labels": True,
                    "diarize": diarize,
                    "smart_formatting": True,
                    "summarize": summarize,
                    "model": "whisper-large",
                },
            )
            audio.close()
        return response
    except Exception as e:
        logger.error("Error transcribing audio to text")
        logger.error(e)
        return


def create_transcript(data):
    result = ""
    for x in data:
        result = result + x[2] + " "

    return result


def initialize():
    logger = logging.getLogger(__app_name__)
    try:
        # FFMPEG installed on first use.
        logger.debug("Initializing FFMPEG...")
        static_ffmpeg.add_paths()
        logger.debug("Initialized FFMPEG")
    except Exception as e:
        logger.error("Error initializing")
        logger.error(e)


def write_to_file(
    result,
    loc,
    url,
    title,
    date,
    tags,
    category,
    speakers,
    video_title,
    username,
    local,
    test,
    pr,
    summary,
    working_dir="tmp/",
):
    logger = logging.getLogger(__app_name__)
    try:
        transcribed_text = result
        if title:
            file_title = title
        else:
            file_title = video_title
        meta_data = (
            "---\n"
            f"title: {file_title}\n"
            f"transcript_by: {username} via TBTBTC v{__version__}\n"
        )
        if not local:
            meta_data += f"media: {url}\n"
        if tags:
            tags = tags.strip()
            tags = tags.split(",")
            for i in range(len(tags)):
                tags[i] = tags[i].strip()
            meta_data += f"tags: {tags}\n"
        if speakers:
            speakers = speakers.strip()
            speakers = speakers.split(",")
            for i in range(len(speakers)):
                speakers[i] = speakers[i].strip()
            meta_data += f"speakers: {speakers}\n"
        if category:
            category = category.strip()
            category = category.split(",")
            for i in range(len(category)):
                category[i] = category[i].strip()
            meta_data += f"categories: {category}\n"
        if summary:
            meta_data += f"summary: {summary}\n"

        file_name = video_title.replace(" ", "-")
        file_name_with_ext = os.path.join(working_dir, file_name + ".md")

        if date:
            meta_data += f"date: {date}\n"

        meta_data += "---\n"
        if test is not None or pr:
            with open(file_name_with_ext, "a") as opf:
                opf.write(meta_data + "\n")
                opf.write(transcribed_text + "\n")
                opf.close()
        if local:
            url = None
        if not pr:
            generate_payload(
                loc=loc,
                title=file_title,
                transcript=transcribed_text,
                media=url,
                tags=tags,
                category=category,
                speakers=speakers,
                username=username,
                event_date=date,
                test=test,
            )
        return os.path.abspath(file_name_with_ext)
    except Exception as e:
        logger.error("Error writing to file")
        logger.error(e)


def get_md_file_path(
    result,
    loc,
    video,
    title,
    event_date,
    tags,
    category,
    speakers,
    username,
    local,
    video_title,
    test,
    pr,
    summary="",
    working_dir="tmp/",
):
    logger = logging.getLogger(__app_name__)
    try:
        logger.info("writing .md file")
        file_name_with_ext = write_to_file(
            result,
            loc,
            video,
            title,
            event_date,
            tags,
            category,
            speakers,
            video_title,
            username,
            local,
            test,
            pr,
            summary,
            working_dir=working_dir,
        )
        logger.info("wrote .md file")

        absolute_path = os.path.abspath(file_name_with_ext)
        return absolute_path
    except Exception as e:
        logger.error("Error getting markdown file path")
        logger.error(e)


def create_pr(absolute_path, loc, username, curr_time, title):
    logger = logging.getLogger(__app_name__)
    branch_name = loc.replace("/", "-")
    subprocess.call(
        [
            "bash",
            "initializeRepo.sh",
            absolute_path,
            loc,
            branch_name,
            username,
            curr_time,
        ]
    )
    subprocess.call(
        ["bash", "github.sh", branch_name, username, curr_time, title]
    )
    logger.info("Please check the PR for the transcription.")


def get_username():
    logger = logging.getLogger(__app_name__)
    try:
        if os.path.isfile(".username"):
            with open(".username", "r") as f:
                username = f.read()
                f.close()
        else:
            print("What is your github username?")
            username = input()
            with open(".username", "w") as f:
                f.write(username)
                f.close()
        return username
    except Exception as e:
        logger.error("Error getting username")
        logger.error(e)


def check_source_type(source):
    """Returns the type of source based on the file name
    """
    source_type = None
    local = False
    if source.endswith(".mp3") or source.endswith(".wav"):
        source_type = "audio"
    elif check_if_playlist(source):
        source_type = "playlist"
    elif check_if_video(source):
        source_type = "video"
    # check if source is a local file
    if os.path.isfile(source):
        local = True
    return (source_type, local)


def process_audio(
    source,
    title,
    event_date,
    tags,
    category,
    speakers,
    loc,
    model,
    username,
    local,
    test,
    pr,
    deepgram,
    summarize,
    diarize,
    upload=False,
    model_output_dir="local_models/",
    working_dir="tmp/",
):
    logger = logging.getLogger(__app_name__)
    try:
        logger.info("audio file detected")
        curr_time = str(round(time.time() * 1000))

        # check if title is supplied if not, return None
        if title is None:
            logger.error("Error: Please supply a title for the audio file")
            return None
        # process audio file
        summary = None
        result = None
        if not local:
            filename = get_audio_file(
                url=source, title=title, working_dir=working_dir
            )
            abs_path = os.path.abspath(path=filename)
            logger.info(f"filename: {filename}")
            logger.info(f"abs_path: {abs_path}")
        else:
            filename = source.split("/")[-1]
            abs_path = os.path.abspath(source)
        logger.info(f"processing audio file: {abs_path}")
        if filename is None:
            logger.info("File not found")
            return
        if filename.endswith("wav"):
            initialize()
            abs_path = convert_wav_to_mp3(
                abs_path=abs_path, filename=filename, working_dir=working_dir
            )
        if test:
            result = test
        else:
            if deepgram or summarize:
                deepgram_resp = process_mp3_deepgram(
                    filename=abs_path, summarize=summarize, diarize=diarize
                )
                result = get_deepgram_transcript(
                    deepgram_data=deepgram_resp,
                    diarize=diarize,
                    title=title,
                    model_output_dir=model_output_dir,
                    upload=upload,
                )
                if summarize:
                    summary = get_deepgram_summary(deepgram_data=deepgram_resp)
            if not deepgram:
                result = process_mp3(abs_path, model, upload, model_output_dir)
                result = create_transcript(result)
        absolute_path = get_md_file_path(
            result=result,
            loc=loc,
            video=source,
            title=title,
            event_date=event_date,
            tags=tags,
            category=category,
            speakers=speakers,
            username=username,
            local=local,
            video_title=filename[:-4],
            test=test,
            pr=pr,
            summary=summary,
            working_dir=working_dir,
        )

        if pr:
            create_pr(
                absolute_path=absolute_path,
                loc=loc,
                username=username,
                curr_time=curr_time,
                title=title,
            )
        return absolute_path
    except Exception as e:
        logger.error("Error processing audio file")
        logger.error(e)


def process_videos(
    source,
    title,
    event_date,
    tags,
    category,
    speakers,
    loc,
    model,
    username,
    chapters,
    pr,
    deepgram,
    summarize,
    diarize,
    upload=False,
    model_output_dir="local_models",
    working_dir="tmp/",
):
    logger = logging.getLogger(__app_name__)
    try:
        logger.info("Playlist detected")
        if source.startswith("http") or source.startswith("www"):
            parsed_url = urlparse(source)
            source = parse_qs(parsed_url.query)["list"][0]
        url = "https://www.youtube.com/playlist?list=" + source
        logger.info(url)
        videos = get_playlist_videos(url)
        if videos is None:
            logger.info("Playlist is empty")
            return

        selected_model = model + ".en"
        filename = ""

        for video in videos:
            filename = process_video(
                video=video,
                title=title,
                event_date=event_date,
                tags=tags,
                category=category,
                speakers=speakers,
                loc=loc,
                model=selected_model,
                username=username,
                pr=pr,
                chapters=chapters,
                test=False,
                diarize=diarize,
                deepgram=deepgram,
                summarize=summarize,
                upload=upload,
                working_dir=working_dir,
                model_output_dir=model_output_dir,
            )
            if filename is None:
                return None
        return filename
    except Exception as e:
        logger.error("Error processing playlist")
        logger.error(e)


def combine_deepgram_with_chapters(deepgram_data, chapters):
    logger = logging.getLogger(__app_name__)
    try:
        chapters_pointer = 0
        words_pointer = 0
        result = ""
        words = deepgram_data["results"]["channels"][0]["alternatives"][0][
            "words"
        ]
        # chapters index, start time, name
        # transcript start time, end time, text
        while chapters_pointer < len(chapters) and words_pointer < len(words):
            if chapters[chapters_pointer][1] <= words[words_pointer]["end"]:
                result = (
                    result + "\n\n## " + chapters[chapters_pointer][2] + "\n\n"
                )
                chapters_pointer += 1
            else:
                result = result + words[words_pointer]["punctuated_word"] + " "
                words_pointer += 1

        # Append the final chapter heading and remaining content
        while chapters_pointer < len(chapters):
            result = result + "\n\n## " + chapters[chapters_pointer][2] + "\n\n"
            chapters_pointer += 1
        while words_pointer < len(words):
            result = result + words[words_pointer]["punctuated_word"] + " "
            words_pointer += 1

        return result
    except Exception as e:
        logger.error("Error combining deepgram with chapters")
        logger.error(e)


def process_video(
    video,
    title,
    event_date,
    tags,
    category,
    speakers,
    loc,
    model,
    username,
    chapters,
    test,
    pr,
    local=False,
    deepgram=False,
    summarize=False,
    diarize=False,
    upload=False,
    model_output_dir="local_models",
    working_dir="tmp/",
):
    logger = logging.getLogger(__app_name__)
    try:
        curr_time = str(round(time.time() * 1000))
        if not local:
            if "watch?v=" in video:
                parsed_url = urlparse(video)
                video = parse_qs(parsed_url.query)["v"][0]
            elif "youtu.be" in video or "embed" in video:
                video = video.split("/")[-1]
            video = "https://www.youtube.com/watch?v=" + video
            logger.info("Transcribing video: " + video)
            if event_date is None:
                event_date = get_date(video)
            abs_path = download_video(url=video, working_dir=working_dir)
            if abs_path is None:
                logger.info("File not found")
                return None
            filename = abs_path.split("/")[-1]
        else:
            filename = video.split("/")[-1]
            logger.info("Transcribing video: " + filename)
            abs_path = os.path.abspath(video)

        if not title:
            title = filename[:-4]
        initialize()
        summary = None
        result = ""
        deepgram_data = None
        if chapters and not test:
            chapters = read_description(working_dir)
        elif test:
            chapters = read_description("test/testAssets/")
        mp3_path = convert_video_to_mp3(abs_path, working_dir)
        if deepgram or summarize:
            deepgram_data = process_mp3_deepgram(
                filename=mp3_path, summarize=summarize, diarize=diarize
            )
            result = get_deepgram_transcript(
                deepgram_data=deepgram_data,
                diarize=diarize,
                title=title,
                model_output_dir=model_output_dir,
                upload=upload,
            )
            if summarize:
                logger.info("Summarizing")
                summary = get_deepgram_summary(deepgram_data=deepgram_data)
        if not deepgram:
            result = process_mp3(mp3_path, model, upload, model_output_dir)
        if chapters and len(chapters) > 0:
            logger.info("Chapters detected")
            write_chapters_file(
                os.path.join(working_dir, filename[:-4] + ".chapters"), chapters
            )
            if deepgram:
                if diarize:
                    result = combine_deepgram_chapters_with_diarization(
                        deepgram_data=deepgram_data, chapters=chapters
                    )
                else:
                    result = combine_deepgram_with_chapters(
                        deepgram_data=deepgram_data, chapters=chapters
                    )
            else:
                result = combine_chapter(
                    chapters=chapters,
                    transcript=result,
                    working_dir=working_dir,
                )
        else:
            if not test and not deepgram:
                result = create_transcript(result)
            elif not deepgram:
                result = ""
        logger.info("Creating markdown file")
        absolute_path = get_md_file_path(
            result=result,
            loc=loc,
            video=video,
            title=title,
            event_date=event_date,
            tags=tags,
            summary=summary,
            category=category,
            speakers=speakers,
            username=username,
            video_title=filename[:-4],
            local=local,
            pr=pr,
            test=test,
            working_dir=working_dir,
        )
        if not test:
            if pr:
                create_pr(
                    absolute_path=absolute_path,
                    loc=loc,
                    username=username,
                    curr_time=curr_time,
                    title=title,
                )
        return absolute_path
    except Exception as e:
        logger.error("Error processing video")
        logger.error(e)



def process_source(
    source,
    title,
    event_date,
    tags,
    category,
    speakers,
    loc,
    model,
    username,
    source_type,
    chapters,
    local,
    test=None,
    pr=False,
    deepgram=False,
    summarize=False,
    diarize=False,
    upload=False,
    model_output_dir=None,
    verbose=False,
):
    tmp_dir = tempfile.mkdtemp()
    model_output_dir = (
        "local_models/" if model_output_dir is None else model_output_dir
    )

    try:
        if source_type == "audio":
            filename = process_audio(
                source=source,
                title=title,
                event_date=event_date,
                tags=tags,
                category=category,
                speakers=speakers,
                loc=loc,
                model=model,
                username=username,
                summarize=summarize,
                local=local,
                test=test,
                pr=pr,
                deepgram=deepgram,
                diarize=diarize,
                upload=upload,
                model_output_dir=model_output_dir,
                working_dir=tmp_dir,
            )
        elif source_type == "playlist":
            filename = process_videos(
                source=source,
                title=title,
                event_date=event_date,
                tags=tags,
                category=category,
                speakers=speakers,
                loc=loc,
                model=model,
                username=username,
                summarize=summarize,
                chapters=chapters,
                pr=pr,
                deepgram=deepgram,
                diarize=diarize,
                upload=upload,
                model_output_dir=model_output_dir,
                working_dir=tmp_dir,
            )
        elif source_type == "video":
            filename = process_video(
                video=source,
                title=title,
                event_date=event_date,
                summarize=summarize,
                tags=tags,
                category=category,
                speakers=speakers,
                loc=loc,
                model=model,
                username=username,
                local=local,
                diarize=diarize,
                chapters=chapters,
                test=test,
                pr=pr,
                deepgram=deepgram,
                upload=upload,
                model_output_dir=model_output_dir,
                working_dir=tmp_dir,
            )
        else:
            raise Exception(f"{source_type} is not a valid source type")
        return filename, tmp_dir
    except Exception as e:
        logger.error("Error processing source")
        logger.error(e)


def get_date(url):
    video = pytube.YouTube(url)
    return str(video.publish_date).split(" ")[0]


def clean_up(tmp_dir):
    try:
        shutil.rmtree(tmp_dir)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise


def save_local_json(json_data, title, model_output_dir):
    logger = logging.getLogger(__app_name__)
    logger.info(f"Saving Locally...")
    time_in_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    if not os.path.isdir(model_output_dir):
        os.makedirs(model_output_dir)
    file_path = os.path.join(
        model_output_dir, title + "_" + time_in_str + ".json"
    )
    with open(file_path, "w") as json_file:
        json.dump(json_data, json_file, indent=4)
    logger.info(f"Model stored at path {file_path}")
    return file_path


def generate_srt(data, filename, model_output_dir):
    logger = logging.getLogger(__app_name__)
    logger.info("Saving Locally...")
    time_in_str = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    base_filename, _ = os.path.splitext(filename)
    if not os.path.isdir(model_output_dir):
        os.makedirs(model_output_dir)
    output_file = os.path.join(
        model_output_dir, base_filename + "_" + time_in_str + ".srt"
    )
    logger.debug(f"writing srt to {output_file}")
    with open(output_file, "w") as f:
        for index, segment in enumerate(data):
            start_time, end_time, text = segment
            f.write(f"{index+1}\n")
            f.write(f"{format_time(start_time)} --> {format_time(end_time)}\n")
            f.write(f"{text.strip()}\n\n")
    logger.info("File saved")
    return output_file


def format_time(time):
    hours = int(time / 3600)
    minutes = int((time % 3600) / 60)
    seconds = int(time % 60)
    milliseconds = int((time % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def upload_file_to_s3(file_path):
    logger = logging.getLogger(__app_name__)
    s3 = boto3.client("s3")
    config = dotenv_values(".env")
    bucket = config["S3_BUCKET"]
    base_filename = file_path.split("/")[-1]
    dir = "model outputs/" + base_filename
    try:
        s3.upload_file(file_path, bucket, dir)
        logger.info(f"File uploaded to S3 bucket : {bucket}")
    except Exception as e:
        logger.error(f"Error uploading file to S3 bucket: {e}")


def generate_payload(
    loc,
    title,
    event_date,
    tags,
    category,
    speakers,
    username,
    media,
    transcript,
    test,
):
    logger = logging.getLogger(__app_name__)
    try:
        event_date = (
            event_date
            if event_date is None
            else event_date
            if type(event_date) is str
            else event_date.strftime("%Y-%m-%d")
        )
        data = {
            "title": title,
            "transcript_by": f"{username} via TBTBTC v{__version__}",
            "categories": category,
            "tags": tags,
            "speakers": speakers,
            "date": event_date,
            "media": media,
            "loc": loc,
            "body": transcript,
        }
        content = {"content": data}
        if test:
            return content
        else:
            config = dotenv_values(".env")
            url = config["QUEUE_ENDPOINT"] + "/api/transcripts"
            resp = requests.post(url, json=content)
            if resp.status_code == 200:
                logger.info("Transcript added to queue")
            return resp
    except Exception as e:
        logger.error(e)
