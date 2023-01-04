"""This module provides the transcript cli."""
# yttbtc/cli.py

import urllib.request
import json
import urllib
from typing import Optional
import typer
from requests_html import HTMLSession
from yttbtc import __app_name__, __version__
import subprocess
import pytube
from moviepy.editor import VideoFileClip
import pywhisper
import os
import static_ffmpeg

app = typer.Typer()

session = HTMLSession()
os.environ["IMAGEIO_FFMPEG_EXE"] = "/usr/bin/ffmpeg"

def download_video(url):
    video = pytube.YouTube(url)
    stream = video.streams.get_by_itag(18)
    stream.download()
    return stream.default_filename


def convert_to_mp3(filename):
    clip = VideoFileClip(filename)
    clip.audio.write_audiofile(filename[:-4] + ".mp3")
    clip.close()


def AudiotoText(filename):
    model = pywhisper.load_model("base")
    result = model.transcribe(filename)
    print(result["text"])
    sonuc = result["text"]
    return sonuc


def convert(link, model):
    print('''
    This tool will convert Youtube videos to mp3 files and then transcribe them to text using Whisper.
    ''')
    print("URL: " + link)
    print("MODEL: " + model)
    # FFMPEG installed on first use.
    print("Initializing FFMPEG...")
    static_ffmpeg.add_paths()

    print("Downloading video... Please wait.")
    try:
        filename = download_video(link)
        print("Downloaded video as " + filename)
    except:
        print("Not a valid link..")
        return
    try:
        convert_to_mp3(filename)
        print("Converted video to mp3")
    except:
        print("Error converting video to mp3")
        return
    try:
        mymodel = pywhisper.load_model(model)
        result = mymodel.transcribe(filename[:-4] + ".mp3")
        print(result["text"])
        result = result["text"]
        os.remove(filename)
        os.remove(filename[:-4] + ".mp3")
        print("Removed video and audio files")
        print("Done!")
        return result
    except Exception as e:
        print("Error transcribing audio to text")
        print(e)
        return


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{__app_name__} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
        version: Optional[bool] = typer.Option(
            None,
            "--version",
            "-v",
            help="Show the application's version and exit.",
            callback=_version_callback,
            is_eager=True,
        )
) -> None:
    return


@app.command()
def yt2btc(
        video_id: str,
        file_name: str
) -> None:
    """Add a transcription"""
    file_name = file_name.replace("/", "-")
    file_name_with_ext = file_name + '.md'
    outls = []

    url = "https://www.youtube.com/watch?v=" + video_id
    result = convert(url, 'base.en')
    
    query_string = urllib.parse.urlencode({"format": "json", "url": url})
    full_url = "https://www.youtube.com/oembed" + "?" + query_string
    
    with urllib.request.urlopen(full_url) as response:
        response_text = response.read()
        data = json.loads(response_text.decode())
        title = data['title']
    
    meta_data = '---\n' \
                f'title: {title} ' + '\n' \
                                     f'transcript_by: youtube_to_bitcoin_transcript_v_{__version__}\n' \
                                     f'media: {url}\n' \
                                     '---\n'
    with open(file_name_with_ext, 'a') as opf:
        opf.write(meta_data + '\n')
        opf.write(result + '\n')
     
    absolute_path = os.path.abspath(file_name_with_ext)

    """ INITIALIZE AND OPEN A PR"""
    print("Initializing git and creating a repo \n")
    subprocess.call(['bash', 'github.sh', file_name_with_ext, file_name, absolute_path])
