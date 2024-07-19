import os

import configparser
from dotenv import load_dotenv


def read_config(profile):
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config[profile]

class Settings:
    def __init__(self):
        # Reload environment variables from .env file
        load_dotenv(override=True)
        # server
        self.TSTBTC_METADATA_DIR = os.getenv('TSTBTC_METADATA_DIR')
        self.BITCOINTRANSCRIPTS_DIR = os.getenv('BITCOINTRANSCRIPTS_DIR')
        # cli
        self.TRANSCRIPTION_SERVER_URL = os.getenv('TRANSCRIPTION_SERVER_URL')

        # Load configuration from config.ini
        self.PROFILE = os.getenv('PROFILE', 'DEFAULT')
        self.config = read_config(self.PROFILE)

    @staticmethod
    def _get_env_variable(var_name, custom_message=None):
        value = os.getenv(var_name)
        if not value:
            error_message = custom_message or \
                f"{var_name} is not set in the environment or .env file. Please set it and restart the server."
            raise Exception(error_message)
        return value

    @property
    def DEEPGRAM_API_KEY(self):
        return self._get_env_variable('DEEPGRAM_API_KEY',
            "To use Deepgram as a transcription service you need to define a 'DEEPGRAM_API_KEY' in your .env file")

    @property
    def BTC_TRANSCRIPTS_URL(self):
        return self._get_env_variable('BTC_TRANSCRIPTS_URL')
    

    @property
    def S3_BUCKET(self):
        return self._get_env_variable('S3_BUCKET')

    @property
    def QUEUE_ENDPOINT(self):
        return self._get_env_variable('QUEUE_ENDPOINT')

    @property
    def BEARER_TOKEN(self):
        return self._get_env_variable('BEARER_TOKEN')

# Initialize the Settings class and expose an instance
settings = Settings()

__all__ = ['settings']
