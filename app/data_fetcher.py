import json
import os
import requests
from typing import Dict, Literal, Optional, List

from app import (
    logging
)
from app.types import SourceType, TranscriptionCoverage

logger = logging.get_logger()


class DataFetcher:
    """
    The DataFetcher class is responsible for retrieving and caching JSON data from Bitcoin Transcripts,
    which serve as the source of truth for various transcription-related information. It provides methods
    to fetch data on transcription status, sources, existing media, speakers, and tags, ensuring efficient
    data retrieval and reducing redundant network requests through caching.
    """

    def __init__(self, base_url: str, cache_dir: Optional[str] = "cache/"):
        self.base_url = base_url
        self.cache_dir = cache_dir
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

    def fetch_json(self, name: Literal['status', 'sources', 'directories'], cache: bool = False):
        """Fetches JSON data from a configured URL or local cache"""
        cached_file_path = os.path.join(
            self.cache_dir, f"{name}.json") if self.cache_dir else None

        if cache and cached_file_path and os.path.exists(cached_file_path):
            # Load data from the local file
            logger.debug(f"Fetched data from {cached_file_path}")
            with open(cached_file_path, "r") as file:
                return json.load(file)

        # Fetch data from the remote URL
        url = f"{self.base_url}/{name}.json"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            logger.debug(f"Fetched data from {url} (cache={cache})")
            if cache and cached_file_path:
                # Store the fetched data locally
                with open(cached_file_path, "w") as file:
                    json.dump(data, file)
            return data
        else:
            raise Exception(
                f"Failed to fetch data from {url}. Status code: {response.status_code}")

    def get_existing_media(self) -> Dict[str, bool]:
        """Returns a dictionary of existing media"""
        data = self.fetch_json("status")
        return {value: True for value in data.get("existing", {}).get("media", [])}

    def get_transcription_backlog(self) -> List[str]:
        """Returns a list of items that need transcription"""
        data = self.fetch_json("status")
        return data.get("needs", {}).get("transcript", [])

    def get_sources(self, loc: str, transcription_coverage: TranscriptionCoverage, cache: bool = False) -> list[SourceType]:
        """Returns filtered sources based on location and transcription coverage"""
        data: list[SourceType] = self.fetch_json('sources', cache)
        filtered_data = [
            source for source in data if source['loc'] == loc or loc == 'all']
        if transcription_coverage != 'none':
            filtered_data = [source for source in filtered_data if source.get(
                'transcription_coverage') == transcription_coverage]
        return filtered_data

    def get_speakers(self) -> List[str]:
        """Returns a list of existing speakers"""
        data = self.fetch_json("status")
        return data.get("existing", {}).get("speakers", [])

    def get_tags(self) -> List[str]:
        """Returns a list of existing tags"""
        data = self.fetch_json("status")
        return data.get("existing", {}).get("tags", [])
