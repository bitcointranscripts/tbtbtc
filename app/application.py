"""This module provides the transcript cli."""
import errno
import logging
import shutil

import boto3

from app import __app_name__, __version__
from app.config import settings
from app.logging import get_logger

logger = get_logger()


def clean_up(tmp_dir):
    try:
        shutil.rmtree(tmp_dir)
    except OSError as exc:
        if exc.errno != errno.ENOENT:
            raise


def upload_file_to_s3(file_path):
    logger = logging.getLogger(__app_name__)
    s3 = boto3.client("s3")
    bucket = settings.S3_BUCKET
    base_filename = file_path.split("/")[-1]
    dir = "model outputs/" + base_filename
    try:
        s3.upload_file(file_path, bucket, dir)
        logger.info(f"File uploaded to S3 bucket : {bucket}")
    except Exception as e:
        logger.error(f"Error uploading file to S3 bucket: {e}")
