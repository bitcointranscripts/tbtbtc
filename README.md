# TRANSCRIBER TO BITCOIN TRANSCRIPT

This cli app transcribes audio and video for submission to the [bitcointranscripts](https://github.com/bitcointranscripts/bitcointranscripts) repo. 

**Available transcription models and services**

- (local) Whisper `--model xxx [default: tiny.en]`
- (remote) Deepgram (whisper-large) `--deepgram [default: False]`
  - summarization `--summarize`
  - diarization `--diarize`

**Transcription Workflow**

This transcription tool operates through a structured four-stage process:

1. Preprocess: Gathers all the available metadata for each source (supports YouTube videos&playlists, and RSS feeds)
2. Process: Downloads and converts sources for transcription preparation
3. Transcription: Utilizes [`openai-whisper`](https://github.com/openai/whisper) or [Deepgram](https://deepgram.com/) to generate transcripts.
    1. Converts audio to text.
        - Save as JSON: Preserves the output of the transcription service for future use.
        - Save as SRT: Generates SRT file [whisper only]
    2. Summarize: Generates a summary of the transcript. [deepgram only]
    3. Upload: Saves transcription service output in an AWS S3 Bucket [optional]
    4. Finalizes the resulting transcript.
        - Process diarization. [deepgram only]
        - Process chapters.
4. Postprocess: Offers multiple options for further actions:
    - **Push to GitHub**: Push transcripts to your fork of the [bitcointranscripts](https://github.com/bitcointranscripts/bitcointranscripts) repo.
    - **Markdown**: Saves transcripts in a markdown format supported by bitcointranscripts.
    - **Upload**: Saves transcripts in an AWS S3 Bucket.
    - **Push to Queuer backend**: Sends transcripts to [a Queuer backend](https://github.com/bitcointranscripts/transcription-review-backend).
    - **Save as JSON**: Preserves transcripts for future use.


## Prerequisites

- This tool requires a running server component. Make sure you have the server running before using the CLI commands. You need to set the `TRANSCRIPTION_SERVER_URL` in your `.env` file. This should point to the URL where your transcription server is running (e.g., `http://localhost:8000`).

- To use [deepgram](https://deepgram.com/) as a transcription service,
  you must have a valid `DEEPGRAM_API_KEY` in the `.env` file.

- To push the resulting transcript to GitHub you need to fork
  [bitcointranscripts](https://github.com/bitcointranscripts/bitcointranscripts)
  and then clone your fork and define your `BITCOINTRANSCRIPTS_DIR` in the `.env` file.

- To push the resulting transcript to a Queuer backend, you must have a 
  valid `QUEUE_ENDPOINT` in the `.env` file. If not, you can instead save
  the payload in a json file using the `--noqueue` flag.

- To enable pushing the models to a S3 bucket,
    - [Install](https://aws.amazon.com/cli/) aws-cli to your system.
    - [Configure](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
      aws-cli by first generating IAM credentials (if not already present) and
      using `aws configure` to set them.
    - To verify proper configuration, run `aws s3 ls` to show the list of S3
      buckets. Don't forget to set a valid `S3_BUCKET` in the `.env` file.

- To be able to convert the intermediary media files to mp3, install `FFmpeg`

    - for Mac Os users, run `brew install ffmpeg`

    - for other users, follow the instruction on
      their [site](https://ffmpeg.org/) to install

- To use a specific [configuration profile](#configuration), set the `PROFILE` variable in your `.env` file.


## Configuration

This application supports configuration via a `config.ini` file.
This file allows you to set default values for various options and flags, reducing the need to specify them on the command line every time.
Additionally, the configuration file can include options not available through the command line, offering greater flexibility and control over the application's behavior.

### Creating a Configuration File

An example configuration file named `config.ini.example` is included in the repository.
To use it, copy it to `config.ini` and modify it according to your needs:
```sh
cp config.ini.example config.ini
```

## Installation and Setup

Navigate to the application directory and run the below commands:

1. `python3 -m venv venv` creates a virtual environment
2. `source venv/bin/activate` activates the virtual environment
3. `pip3 install .` to install the application
   - To include Whisper support, use: `pip3 install .[whisper]`
4. Create a `.env` file in the project root and add the required variables based on [Prerequisites](#prerequisites).
5. `tstbtc --version` view the application version
6. `tstbtc --help` view the application help

To uninstall: `pip3 uninstall tstbtc`

## Usage

The application has a server component that needs to be running for the CLI to function.
This allows the heavy lifting of transcription to be done on a separate machine if desired.

### Starting the Server

To start the server, navigate to the application directory and run:

```sh
tstbtc-server prod
```

The server will be accessible at `http://localhost:8000` by default.
Ensure this matches the `TRANSCRIPTION_SERVER_URL` in your `.env` file.

### Using the CLI

Once the server is running, you can use the CLI commands.

`tstbtc transcribe {source_file/url}` transcribe the given source

Suported sources:
  - YouTube videos and playlists
  - Local and remote audio files
  - JSON files containing individual sources

Note:
- The https links need to be wrapped in quotes when running the command on zsh

To include optional metadata in your transcript, you can add the following
parameters:

- `--loc`: Add the location in the bitcointranscripts hierarchy that you want to associate the transcript [default: "misc"]
- `-t` or `--title`: Add the title for the resulting transcript (required for audio files)
- `-d` or `--date`: Add the event date to transcript's metadata in format 'yyyy-mm-dd'
- can be used multiple times:
  - `-T` or `--tags`: Add a tag to transcript's metadata
  - `-s` or `--speakers`: Add a speaker to the transcript's metadata
  - `-c` or `--category`: Add a category to the transcript's metadata

To configure the transcription process, you can use the following flags:

- `-m` or `--model`: Select which whisper model to use for the transcription [default: tiny.en]
- `-D` or `--deepgram`: Use deepgram for transcription, instead of using the whisper model [default: False]
- `-M` or `--diarize`: Supply this flag if you have multiple speakers AKA want to diarize the content [only available with deepgram]
- `-S` or `--summarize`: Summarize the transcript [only available with deepgram]
- `--github`: Specify the GitHub operation mode
- `-u` or `--upload`: Upload processed model files to AWS S3
- `--markdown`: Save the resulting transcript to a markdown format supported by bitcointranscripts
- `--noqueue`: Do not push the resulting transcript to the Queuer, instead store the payload in a json file
- `--nocleanup`: Do not remove temp files on exit

### Examples

To transcribe [this podcast episode](https://www.youtube.com/watch?v=Nq6WxJ0PgJ4) from YouTube
from Stephan Livera's podcast and add the associated metadata, we would run either
of the below commands. The first uses short argument tags, while the second uses
long argument tags. The result is the same.

- `tstbtc transcribe Nq6WxJ0PgJ4 --loc "stephan-livera-podcast" -t 'OP_Vault - A New Way to HODL?' -d '2023-01-30' -T 'script' -T 'op_vault' -s 'James O’Beirne' -s 'Stephan Livera' -c ‘podcast’`
- `tstbtc transcribe Nq6WxJ0PgJ4 --loc "stephan-livera-podcast" --title 'OP_Vault - A New Way to HODL?' --date '2023-01-30' --tags 'script' --tags 'op_vault' --speakers 'James O’Beirne' --speakers 'Stephan Livera' --category ‘podcast’`

You can also transcribe a remote audio/mp3 link, such as the following from Stephan Livera's podcast: 
```shell
mp3_link="https://anchor.fm/s/7d083a4/podcast/play/64348045/https%3A%2F%2Fd3ctxlq1ktw2nl.cloudfront.net%2Fstaging%2F2023-1-1%2Ff7fafb12-9441-7d85-d557-e9e5d18ab788.mp3"
tstbtc transcribe $mp3_link --loc "stephan-livera-podcast" --title 'SLP455 Anant Tapadia - Single Sig or Multi Sig?' --date '2023-02-01' --tags 'multisig' --speakers 'Anant Tapadia' --speakers 'Stephan Livera' --category 'podcast'
```

## Docker Support

This application can be run using Docker Compose, which simplifies the process of running both the server and CLI components.

Quick start:

1. Start the server:
   ```sh
   docker-compose up server
   ```

2. Use the CLI:
   ```sh
   docker-compose run --rm cli [command] [arguments]
   ```

For detailed instructions on using Docker with this project, including how to work with local files, environment variables, and custom builds, please refer to our [Docker Guide](docs/docker-guide.md).


## Testing

To run the unit tests

`pytest -v -m main -s`

To run the feature tests

`pytest -v -m feature -s`

To run the full test suite

`pytest -v -s`


## License

Transcriber to Bitcoin Transcript is released under the terms of the MIT
license. See [LICENSE](LICENSE) for more information or
see https://opensource.org/licenses/MIT.
