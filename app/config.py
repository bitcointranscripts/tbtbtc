import configparser
from dotenv import dotenv_values
from fastapi import HTTPException

def get_btc_transcripts_url():
    config = dotenv_values(".env")
    url = config.get("BTC_TRANSCRIPTS_URL")
    if not url:
        raise HTTPException(
            status_code=500,
            detail="BTC_TRANSCRIPTS_URL is not set in the environment or .env file. "
                   "Please set it and restart the server."
        )
    return url

def read_config(profile='DEFAULT'):
    config = configparser.ConfigParser()
    config.read('config.ini')

    return config[profile]

# Get the current profile from an environment variable or default to 'DEFAULT'
env = dotenv_values(".env")
config = read_config(env.get("PROFILE", "DEFAULT"))
