import os
import tempfile

import yaml
import yt_dlp

from app.config import settings
from app.exceptions import DuplicateSourceError
from app.transcript import (
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
from app.data_writer import DataWriter
from app.data_fetcher import DataFetcher
from app.github_api_handler import GitHubAPIHandler


class Transcription:
    def __init__(
        self,
        model="tiny",
        github=False,
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
        self.nocleanup = nocleanup
        self.status = "idle"  # Can be "idle", "in_progress", or "completed"
        self.test_mode = test_mode
        self.logger = get_logger()
        self.tmp_dir = working_dir if working_dir is not None else tempfile.mkdtemp()

        self.transcript_by = self.__configure_username(username)
        # during testing we need to create the markdown for validation purposes
        self.markdown = markdown or test_mode
        self.metadata_writer = DataWriter(
            self.__configure_tstbtc_metadata_dir())
        self.github = github
        self.github_handler = None
        if self.github:
            self.github_handler = GitHubAPIHandler()
        self.review_flag = self.__configure_review_flag(needs_review)
        if deepgram:
            self.service = services.Deepgram(
                summarize, diarize, upload, self.metadata_writer)
        else:
            self.service = services.Whisper(model, upload, self.metadata_writer)
        self.model_output_dir = model_output_dir
        self.transcripts: list[Transcript] = []
        # during testing we do not have/need a queuer backend
        self.queuer = Queuer(test_mode=test_mode) if queue is True else None
        self.existing_media = None
        self.preprocessing_output = [] if batch_preprocessing_output else None
        self.data_fetcher = DataFetcher(base_url="http://btctranscripts.com")

        self.logger.debug(f"Temp directory: {self.tmp_dir}")

    def _create_subdirectory(self, subdir_name):
        """Helper method to create subdirectories within the central temp director"""
        subdir_path = os.path.join(self.tmp_dir, subdir_name)
        os.makedirs(subdir_path)
        return subdir_path

    def __configure_tstbtc_metadata_dir(self):
        metadata_dir = settings.TSTBTC_METADATA_DIR
        if not metadata_dir:
            alternative_metadata_dir = "metadata/"
            self.logger.debug(
                f"'TSTBTC_METADATA_DIR' environment variable is not defined. Metadata will be stored at '{alternative_metadata_dir}'.")
            return alternative_metadata_dir
        return metadata_dir

    def __configure_review_flag(self, needs_review):
        # sanity check
        if needs_review and not self.markdown:
            raise Exception(
                "The `--needs-review` flag is only applicable when creating a markdown")

        if needs_review or self.github_handler:
            return " --needs-review"
        else:
            return ""

    def __configure_username(self, username: str | None):
        if self.test_mode:
            return "username"
        if username:
            return username
        else:
            raise Exception("You need to provide a username for transcription attribution")

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
        additional_resources=[],
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
            self.logger.debug(
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

        self.logger.debug(f"Adding transcripts from {json_file}")
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

        self.logger.debug(f"Removing transcripts from {json_file}")
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
        try:
            for transcript in self.transcripts:
                transcript.status = "in_progress"
                output_dir = f"{self.model_output_dir}/{transcript.source.loc}"
                self.logger.info(
                    f"Processing source: {transcript.source.source_file}")
                transcript.tmp_dir = self._create_subdirectory(
                    f"transcript-{utils.slugify(transcript.title)}")
                transcript.process_source(transcript.tmp_dir)
                if self.test_mode:
                    transcript.outputs["raw"] = test_transcript if test_transcript is not None else "test-mode"
                else:
                    self.service.transcribe(transcript)
                transcript.status = "completed"
                self.postprocess(transcript)

            self.status = "completed"
            if self.github:
                self.push_to_github(self.transcripts)
            return self.transcripts
        except Exception as e:
            self.status = "failed"
            raise Exception(f"Error with the transcription: {e}") from e

    def push_to_github(self, transcripts: list[Transcript]):
        if not self.github_handler:
            return

        pr_url_transcripts = self.github_handler.push_transcripts(transcripts)
        if pr_url_transcripts:
            self.logger.info(f"transcripts: Pull request created: {pr_url_transcripts}")
            pr_url_metadata = self.github_handler.push_metadata(transcripts, pr_url_transcripts)
            if pr_url_metadata:
                self.logger.info(f"metadata: Pull request created: {pr_url_metadata}")
            else:
                self.logger.error("metadata: Failed to create pull request.")
        else:
            self.logger.error("transcripts: Failed to create pull request.")

    def write_to_markdown_file(self, transcript: Transcript, output_dir):
        """Writes transcript to a markdown file and returns its absolute path
        This file is the one submitted as part of the Pull Request to the
        bitcointranscripts repo
        """
        class IndentedListDumper(yaml.Dumper):
            """
            Custom YAML Dumper that ensures lists are always indented.
            This is necessary because the default YAML dumper does not indent lists
            when they are nested inside a mapping/dictionary.
            """
            def increase_indent(self, flow=False, indentless=False):
                return super(IndentedListDumper, self).increase_indent(flow, False)

        self.logger.debug("Creating markdown file with transcription...")
        try:
            if transcript.outputs["raw"] is None:
                raise Exception("No transcript found")
            
            # Get the metadata from the source
            metadata = transcript.source.to_json()

            # Add or modify specific fields
            metadata['transcript_by'] = f"{self.transcript_by} via tstbtc v{__version__}{self.review_flag}"
            
            # List of fields to exclude from the markdown metadata
            excluded_fields = ['type', 'loc', 'chapters', 'description']

            # Remove excluded fields from the metadata
            for field in excluded_fields:
                metadata.pop(field, None)

            # Convert metadata to YAML
            yaml_metadata = yaml.dump(metadata, Dumper=IndentedListDumper, sort_keys=False)
            
            # Prepare the full content
            full_content = f"---\n{yaml_metadata}---\n\n{transcript.outputs['raw']}\n"
            
            # Write to file
            markdown_file = f"{utils.configure_output_file_path(output_dir, transcript.title, add_timestamp=False)}.md"
            with open(markdown_file, "w") as opf:
                opf.write(full_content)
            
            self.logger.info(f"Markdown file stored at: {markdown_file}")
            return os.path.abspath(markdown_file)
        except Exception as e:
            raise Exception(f"Error writing to file: {e}")

    def write_to_json_file(self, transcript: Transcript):
        self.logger.debug("Creating JSON file with transcription...")
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

    def postprocess(self, transcript: Transcript) -> None:
        try:
            output_dir = f"{self.model_output_dir}/{transcript.source.loc}"
            if self.markdown or self.github_handler:
                transcript.outputs["markdown"] = self.write_to_markdown_file(
                    transcript,
                    output_dir if not self.test_mode else transcript.tmp_dir)
            elif not self.test_mode:
                transcript_json = transcript.to_json()
                transcript_json["transcript_by"] = f"{self.transcript_by} via tstbtc v{__version__}"
                if self.queuer:
                    return self.queuer.push_to_queue(transcript_json)
                else:
                    # store payload for the user to manually send it to the queuer
                    transcript.outputs["json"] = self.write_to_json_file(transcript)
        except Exception as e:
            raise Exception(f"Error with postprocessing: {e}") from e

    def clean_up(self):
        self.logger.debug("Cleaning up...")
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
