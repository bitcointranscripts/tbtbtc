import logging as syslogging

import click
import requests

from app import (
    logging,
)
from app.commands.cli_utils import ServerCheckGroup, get_transcription_url
from app.data_writer import DataWriter

logger = logging.get_logger()

data_writer = DataWriter(base_dir="curator/")

@click.group(cls=ServerCheckGroup)
def curator():
    """Curator commands"""
    logging.configure_logger(log_level=syslogging.INFO)
    pass

transcription_coverage = click.option(
    "--coverage",
    type=click.Choice(["full", "none"]),
    default="none",
    show_default=True,
    help="Specify the transcription coverage for filtering sources. "
         "'full' selects sources marked for full transcription. "
         "'none' includes all sources without considering transcription coverage."
)
@curator.command()
@click.argument("loc", nargs=1)
@transcription_coverage
def get_sources(loc, coverage):
    url = get_transcription_url()
    data = {
        "loc": loc,
        "coverage": coverage,
    }
    response = requests.post(f"{url}/curator/get_sources/", json=data)
    result = response.json()
    if response.status_code == 200 and result["status"] == "success":
        file_path = data_writer.write_json(result["data"], "", f"sources_{loc}", True)
        logger.info(f"Data successfully written to {file_path}")
    else:
        logger.error(f"Error: {result.get('detail', 'Unknown error')}")

@curator.command()
def get_transcription_backlog():
    url = get_transcription_url()
    response = requests.post(f"{url}/curator/get_transcription_backlog/")
    result = response.json()
    if response.status_code == 200 and result["status"] == "success":
        if len(result["data"]) == 0:
            logger.info(f"Transcription queue is empty")
            return
        file_path = data_writer.write_json(result["data"], "", f"transcription_backlog", True)
        logger.info(f"Data successfully written to {file_path}")
    else:
        logger.error(f"Error: {result.get('detail', 'Unknown error')}")

commands = curator
