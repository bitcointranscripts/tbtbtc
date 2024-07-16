import click
import requests
from dotenv import dotenv_values

def get_transcription_url():
    config = dotenv_values(".env")
    url = config.get("TRANSCRIPTION_SERVER_URL")
    if not url:
        raise click.ClickException("TRANSCRIPTION_SERVER_URL is not set in the environment or .env file. "
                                   "Please set it and try again.")
    return url

def is_server_running(url):
    try:
        response = requests.get(f"{url}/health", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

class ServerCheckGroup(click.Group):
    def invoke(self, ctx):
        try:
            url = get_transcription_url()
            if not is_server_running(url):
                raise click.ClickException("Transcription server is not running. "
                                           "Please start the server and try again.")
        except click.ClickException as e:
            click.echo(str(e), err=True)
            ctx.exit(1)
        return super().invoke(ctx)
