import os
import shutil
import random
import subprocess
import tempfile

import yaml
import yt_dlp

from app.config import settings
from app.exceptions import DuplicateSourceError
from app.transcript import (
    PostprocessOutput,
    Transcript,
    Source,
    Audio,
    Video,
    Playlist,
    RSS
)
from app import (
    __app_name__,
    __version__,
    application,
    services,
    utils
)
from app.logging import get_logger
from app.queuer import Queuer
from app.types import (
    GitHubMode,
)
from app.data_writer import DataWriter
from app.data_fetcher import DataFetcher


class Transcription:
    def __init__(
        self,
        model="tiny",
        github: GitHubMode = "none",
        summarize=False,
        deepgram=False,
        diarize=False,
        upload=False,
        model_output_dir="local_models/",
        nocleanup=False,
        queue=True,
        markdown=False,
        username=None,
        test_mode=False,
        working_dir=None,
        batch_preprocessing_output=False,
        needs_review=False,
    ):
        self.status = "idle"  # Can be "idle", "in_progress", or "completed"
        self.test_mode = test_mode
        self.logger = get_logger()
        self.tmp_dir = working_dir if working_dir is not None else tempfile.mkdtemp()

        self.transcript_by = "username" if test_mode else self.__get_username()
        # during testing we need to create the markdown for validation purposes
        self.markdown = markdown or test_mode
        self.metadata_writer = DataWriter(
            self.__configure_tstbtc_metadata_dir())
        self.bitcointranscripts_dir = self.__configure_target_repo(github)
        self.review_flag = self.__configure_review_flag(needs_review)
        if deepgram:
            self.service = services.Deepgram(
                summarize, diarize, upload, self.metadata_writer)
        else:
            self.service = services.Whisper(model, upload, self.metadata_writer)
        self.model_output_dir = model_output_dir
        self.transcripts = []
        self.nocleanup = nocleanup
        # during testing we do not have/need a queuer backend
        self.queuer = Queuer(test_mode=test_mode) if queue is True else None
        self.existing_media = None
        self.preprocessing_output = [] if batch_preprocessing_output else None
        self.data_fetcher = DataFetcher(base_url="http://btctranscripts.com")

        self.logger.info(f"Temp directory: {self.tmp_dir}")

    def _create_subdirectory(self, subdir_name):
        """Helper method to create subdirectories within the central temp director"""
        subdir_path = os.path.join(self.tmp_dir, subdir_name)
        os.makedirs(subdir_path)
        return subdir_path

    def __configure_tstbtc_metadata_dir(self):
        metadata_dir = settings.TSTBTC_METADATA_DIR
        if not metadata_dir:
            alternative_metadata_dir = "/metadata"
            self.logger.warning(
                f"'TSTBTC_METADATA_DIR' environment variable is not defined. Metadata will be stored at '{alternative_metadata_dir}'.")
            return alternative_metadata_dir
        return metadata_dir

    def __configure_target_repo(self, github: GitHubMode):
        if github == "none":
            return None
        git_repo_dir = settings.BITCOINTRANSCRIPTS_DIR
        if not git_repo_dir:
            raise Exception(
                "To push to GitHub you need to define a 'BITCOINTRANSCRIPTS_DIR' in your .env file")
        self.github = github
        return git_repo_dir

    def __configure_review_flag(self, needs_review):
        # sanity check
        if needs_review and not self.markdown:
            raise Exception(
                "The `--needs-review` flag is only applicable when creating a markdown")

        if needs_review or self.bitcointranscripts_dir:
            return " --needs-review"
        else:
            return ""

    def __get_username(self):
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
            raise Exception("Error getting username")

    def _initialize_source(self, source: Source, youtube_metadata, chapters):
        """Initialize transcription source based on metadata
        Returns the initialized source (Audio, Video, Playlist)"""

        def check_if_youtube(source: Source):
            """Helper method to check and assign a valid source for
            a YouTube playlist or YouTube video by requesting its metadata
            Does not support video-ids, only urls"""
            try:
                ydl_opts = {
                    'quiet': False,  # Suppress console output
                    'extract_flat': True,  # Extract only metadata without downloading
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info_dict = ydl.extract_info(
                        source.source_file, download=False)
                    if 'entries' in info_dict:
                        # Playlist URL, not a single video
                        # source.title = info_dict["title"]
                        return Playlist(source=source, entries=info_dict["entries"])
                    elif 'title' in info_dict:
                        # Single video URL
                        return Video(source=source)
                    else:
                        raise Exception(source.source_file)

            except Exception as e:
                # Invalid URL or video not found
                raise Exception(f"Invalid source: {e}")
        try:
            if source.source_file.endswith((".mp3", ".wav", ".m4a", ".aac")):
                return Audio(source=source, chapters=chapters)
            if source.source_file.endswith(("rss", ".xml")):
                return RSS(source=source)

            if youtube_metadata is not None:
                # we have youtube metadata, this can only be true for videos
                source.preprocess = False
                return Video(source=source, youtube_metadata=youtube_metadata, chapters=chapters)
            if source.source_file.endswith((".mp4", ".webm")):
                # regular remote video, not youtube
                source.preprocess = False
                return Video(source=source)
            youtube_source = check_if_youtube(source)
            if youtube_source == "unknown":
                raise Exception(f"Invalid source: {source}")
            return youtube_source
        except Exception as e:
            raise Exception(f"Error from assigning source: {e}")

    def _new_transcript_from_source(self, source: Source):
        """Helper method to initialize a new Transcript from source"""
        metadata_file = None
        if source.preprocess:
            if self.preprocessing_output is None:
                # Save preprocessing output for the specific source
                metadata_file = self.metadata_writer.write_json(data=source.to_json(
                ), file_path=source.output_path_with_title, filename='metadata')
            else:
                # Keep preprocessing outputs for later use
                self.preprocessing_output.append(source.to_json())
        # Initialize new transcript from source
        self.transcripts.append(Transcript(
            source=source, test_mode=self.test_mode, metadata_file=metadata_file))

    def add_transcription_source(
        self,
        source_file,
        loc="misc",
        title=None,
        date=None,
        summary=None,
        episode=None,
        additional_resources=None,
        # cutoff_date serves as a threshold, and only content published beyond this point is relevant
        cutoff_date=None,
        tags=[],
        category=[],
        speakers=[],
        preprocess=True,
        youtube_metadata=None,
        link=None,
        chapters=[],
        nocheck=False,
        excluded_media=[]
    ):
        """Add a source for transcription"""
        if cutoff_date:
            cutoff_date = utils.validate_and_parse_date(cutoff_date)
            # Even with a cutoff date, for YouTube playlists we still need to download the metadata
            # for each video in order to obtain the `upload_date` and use it for filtering
            self.logger.info(
                f"A cutoff date of '{cutoff_date}' is given. Processing sources published after this date.")
        preprocess = False if self.test_mode else preprocess
        transcription_sources = {"added": [], "exist": []}
        # check if source is a local file
        local = False
        if os.path.isfile(source_file):
            local = True
        if not nocheck and not local and self.existing_media is None and not self.test_mode:
            self.existing_media = self.data_fetcher.get_existing_media()
        # combine existing media from btctranscripts.com with excluded media given from source
        excluded_media = {value: True for value in excluded_media}
        if self.existing_media is not None:
            excluded_media.update(self.existing_media)
        # initialize source
        # TODO: find a better way to pass metadata into the source
        # as it is, every new metadata field needs to be passed to `Source`
        # I can assign directly after initialization like I do with `additional_resources`
        # but I'm not sure if it's the best way to do it.
        source = self._initialize_source(
            source=Source(source_file=source_file, loc=loc, local=local, title=title, date=date, summary=summary,
                          episode=episode, tags=tags, category=category, speakers=speakers, preprocess=preprocess, link=link),
            youtube_metadata=youtube_metadata,
            chapters=chapters)
        source.additional_resources = additional_resources
        self.logger.debug(f"Detected source: {source}")

        # Check if source is already in the transcription queue
        for transcript in self.transcripts:
            if transcript.source.loc == loc and transcript.source.title == title:
                self.logger.warning(f"Source already exists in queue: {title}")
                raise DuplicateSourceError(loc, title)

        if source.type == "playlist":
            # add a transcript for each source/video in the playlist
            for video in source.videos:
                is_eligible = video.date > cutoff_date if cutoff_date else True
                if video.media not in excluded_media and is_eligible:
                    transcription_sources['added'].append(video.source_file)
                    self._new_transcript_from_source(video)
                else:
                    transcription_sources['exist'].append(video.source_file)
        elif source.type == 'rss':
            # add a transcript for each source/audio in the rss feed
            for entry in source.entries:
                is_eligible = entry.date > cutoff_date if cutoff_date else True
                if entry.media not in excluded_media and is_eligible:
                    transcription_sources['added'].append(entry.source_file)
                    self._new_transcript_from_source(entry)
                else:
                    transcription_sources['exist'].append(entry.source_file)
        elif source.type in ['audio', 'video']:
            if source.media not in excluded_media:
                transcription_sources['added'].append(source.source_file)
                self._new_transcript_from_source(source)
                self.logger.info(
                    f"Source added for transcription: {source.title}")
            else:
                transcription_sources['exist'].append(source.source_file)
                self.logger.info(f"Source already exists ({self.data_fetcher.base_url}): {source.title}")
        else:
            raise Exception(f"Invalid source: {source_file}")
        if source.type in ['playlist', 'rss']:
            self.logger.info(
                f"{source.title}: sources added for transcription: {len(transcription_sources['added'])} (Ignored: {len(transcription_sources['exist'])} sources)")
        return transcription_sources

    def add_transcription_source_JSON(self, json_file, nocheck=False):
        # validation checks
        utils.check_if_valid_file_path(json_file)
        sources = utils.check_if_valid_json(json_file)

        # Check if JSON contains multiple sources
        if not isinstance(sources, list):
            # Initialize an array with 'sources' as the only element
            sources = [sources]

        self.logger.info(f"Adding transcripts from {json_file}")
        for source in sources:
            metadata = utils.configure_metadata_given_from_JSON(source)

            self.add_transcription_source(
                source_file=metadata["source_file"],
                loc=metadata["loc"],
                title=metadata["title"],
                category=metadata["category"],
                tags=metadata["tags"],
                speakers=metadata["speakers"],
                date=metadata["date"],
                summary=metadata["summary"],
                episode=metadata["episode"],
                additional_resources=metadata["additional_resources"],
                youtube_metadata=metadata["youtube_metadata"],
                chapters=metadata["chapters"],
                link=metadata["media"],
                excluded_media=metadata["excluded_media"],
                nocheck=nocheck,
                cutoff_date=metadata["cutoff_date"]
            )

    def remove_transcription_source_JSON(self, json_file):
        # Validate and parse the JSON file
        utils.check_if_valid_file_path(json_file)
        sources = utils.check_if_valid_json(json_file)

        # Check if JSON contains multiple sources
        if not isinstance(sources, list):
            sources = [sources]

        self.logger.info(f"Removing transcripts from {json_file}")
        removed_sources = []

        for source in sources:
            metadata = utils.configure_metadata_given_from_JSON(source)
            loc = metadata["loc"]
            title = metadata["title"]

            for transcript in self.transcripts:
                if transcript.source.loc == loc and transcript.source.title == title:
                    self.transcripts.remove(transcript)
                    removed_sources.append(transcript)
                    self.logger.info(f"Removed source from queue: {title}")
                    break
            else:
                self.logger.warning(f"Source not found in queue: {title}")

        return removed_sources

    def start(self, test_transcript=None):
        self.status = "in_progress"
        self.result = []
        try:
            for transcript in self.transcripts:
                transcript.status = "in_progress"
                output_dir = f"{self.model_output_dir}/{transcript.source.loc}"
                self.logger.info(
                    f"Processing source: {transcript.source.source_file}")
                transcript.tmp_dir = self._create_subdirectory(
                    f"transcript{len(self.result) + 1}")
                transcript.process_source(transcript.tmp_dir)
                if self.test_mode:
                    transcript.result = test_transcript if test_transcript is not None else "test-mode"
                else:
                    transcript = self.service.transcribe(transcript)
                transcript.status = "completed"
                postprocessed_transcript = self.postprocess(transcript)
                self.result.append(postprocessed_transcript)

            self.status = "completed"
            if self.bitcointranscripts_dir:
                self.push_to_github(self.result)
            return self.result
        except Exception as e:
            self.status = "failed"
            raise Exception(f"Error with the transcription: {e}") from e

    def push_to_github(self, outputs: list[PostprocessOutput]):
        # Change to the directory where your Git repository is located
        os.chdir(self.bitcointranscripts_dir)
        if self.github == "remote":
            # Fetch the latest changes from the remote repository
            subprocess.run(['git', 'fetch', 'origin', 'master'])
            # Create a new branch from the fetched 'origin/master'
            branch_name = f"{self.transcript_by}-{''.join(random.choices('0123456789', k=6))}"
            subprocess.run(
                ['git', 'checkout', '-b', branch_name, 'origin/master'])

        # For each output with markdown, create a new commit in the new branch
        for output in outputs:
            if output.get('markdown'):
                markdown_file = output['markdown']
                destination_path = os.path.join(
                    self.bitcointranscripts_dir, output["transcript"].source.loc)
                # Create the destination directory if it doesn't exist
                os.makedirs(destination_path, exist_ok=True)
                # Ensure the markdown file exists before copying
                if os.path.exists(markdown_file):
                    markdown_file_name = os.path.basename(markdown_file)
                    file_base, file_extension = os.path.splitext(
                        markdown_file_name)
                    destination_file_path = os.path.join(
                        destination_path, markdown_file_name)
                    # In case the source has another
                    # transcript with the same name
                    if os.path.exists(destination_file_path):
                        new_file_name = f"{file_base}-2{file_extension}"
                        destination_file_path = os.path.join(
                            destination_path, new_file_name)

                    shutil.copy(markdown_file, destination_file_path)
                    subprocess.run(['git', 'add', destination_file_path])
                    subprocess.run(
                        ['git', 'commit', '-m', f'Add "{output["transcript"].title}" to {output["transcript"].source.loc}'])
                else:
                    print(f"Markdown file {markdown_file} does not exist.")

        if self.github == "remote":
            # Push the branch to the remote repository
            subprocess.run(['git', 'push', 'origin', branch_name])
            # Delete branch locally
            subprocess.run(['git', 'checkout', 'master'])
            subprocess.run(['git', 'branch', '-D', branch_name])

    def write_to_markdown_file(self, transcript: Transcript, output_dir):
        """Writes transcript to a markdown file and returns its absolute path
        This file is the one submitted as part of the Pull Request to the
        bitcointranscripts repo
        """
        self.logger.info("Creating markdown file with transcription...")
        try:
            # Add metadata prefix
            meta_data = (
                "---\n"
                f'title: "{transcript.title}"\n'
                f"transcript_by: {self.transcript_by} via tstbtc v{__version__}{self.review_flag}\n"
            )
            if not transcript.source.local:
                meta_data += f"media: {transcript.source.media}\n"
            meta_data += f"tags: {str(transcript.source.tags)}\n"
            meta_data += f"speakers: {str(transcript.source.speakers)}\n"
            meta_data += f"categories: {str(transcript.source.category)}\n"
            if transcript.summary:
                meta_data += f'summary: "{transcript.summary}"\n'
            if transcript.source.episode:
                meta_data += f"episode: {transcript.source.episode}\n"
            if transcript.source.date:
                meta_data += f"date: {transcript.source.date}\n"

            # Serialize additional_resources to YAML and add to meta_data
            if transcript.source.additional_resources:
                meta_data += "additional_resources:\n"
                for resource in transcript.source.additional_resources:
                    meta_data += yaml.dump([resource], sort_keys=False,
                                           default_flow_style=False, indent=4)

            meta_data += "---\n"

            # Write to file
            markdown_file = f"{utils.configure_output_file_path(output_dir, transcript.title, add_timestamp=False)}.md"
            with open(markdown_file, "w") as opf:
                opf.write(meta_data)
                opf.write(transcript.result + "\n")
            self.logger.info(f"Markdown file stored at: {markdown_file}")
            return os.path.abspath(markdown_file)
        except Exception as e:
            raise Exception(f"Error writing to file: {e}")

    def write_to_json_file(self, transcript: Transcript):
        self.logger.info("Creating JSON file with transcription...")
        output_dir = f"{self.model_output_dir}/{transcript.source.loc}"
        transcript_json = transcript.to_json()
        transcript_json["transcript_by"] = f"{self.transcript_by} via tstbtc v{__version__}"
        json_file = utils.write_to_json(
            transcript_json,
            output_dir,
            f"{transcript.title}_payload"
        )
        self.logger.info(f"Transcription stored at {json_file}")
        return json_file

    def postprocess(self, transcript: Transcript) -> PostprocessOutput:
        try:
            result = {}
            result["transcript"] = transcript
            output_dir = f"{self.model_output_dir}/{transcript.source.loc}"
            if self.markdown or self.bitcointranscripts_dir:
                result["markdown"] = self.write_to_markdown_file(
                    transcript,
                    output_dir if not self.test_mode else transcript.tmp_dir)
            elif not self.test_mode:
                transcript_json = transcript.to_json()
                transcript_json["transcript_by"] = f"{self.transcript_by} via tstbtc v{__version__}"
                if self.queuer:
                    return self.queuer.push_to_queue(transcript_json)
                else:
                    # store payload for the user to manually send it to the queuer
                    result["json"] = self.write_to_json_file(transcript)
            return result
        except Exception as e:
            raise Exception(f"Error with postprocessing: {e}") from e

    def clean_up(self):
        self.logger.info("Cleaning up...")
        application.clean_up(self.tmp_dir)

    def __del__(self):
        if self.nocleanup:
            self.logger.info("Not cleaning up temp files...")
        else:
            self.clean_up()

    def __str__(self):
        excluded_fields = ['logger', "existing_media"]
        fields = {key: value for key, value in self.__dict__.items()
                  if key not in excluded_fields}
        return f"Transcription:{str(fields)}"
