import logging
from pathlib import Path
import sys

from app import __app_name__


def configure_logger(log_level, working_dir=None):
    logger = get_logger()
    sh = logging.StreamHandler()
    sh_log_fmt = '%(asctime)s [%(levelname)s] %(message)s'
    sh.setLevel(log_level)
    sh.setFormatter(logging.Formatter(sh_log_fmt))

    # Always log debug out to a file in the workdir
    if working_dir is not None:
        filehandler = logging.FileHandler(Path(working_dir) / "tstbtc.log")
        filehandler.setLevel(logging.DEBUG)
        file_log_fmt = '%(asctime)s %(name)s [%(levelname)s] %(message)s'
        filehandler.setFormatter(logging.Formatter(file_log_fmt))
        logger.addHandler(filehandler)

    logger.addHandler(sh)
    logger.setLevel(logging.DEBUG)


def get_logger():
    return logging.getLogger(__app_name__)
