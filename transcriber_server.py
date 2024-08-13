import uvicorn
import click

@click.command()
@click.argument('mode', type=click.Choice(['dev', 'prod']))
@click.option('--host', default='0.0.0.0', help='The host to bind to')
@click.option('--port', default=8000, help='The port to bind to')
def run(mode, host, port):
    """Run the server in the specified mode."""
    if mode == 'dev':
        uvicorn.run("server:app", host=host, port=port, reload=True)
    else:
        uvicorn.run("server:app", host=host, port=port)

if __name__ == "__main__":
    run()
