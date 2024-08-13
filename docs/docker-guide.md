# Docker Guide

This guide provides detailed instructions for using Docker with tstbt. It covers both the server and CLI components, and includes information on working with local files, environment variables, and custom builds.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Running with Docker Compose](#running-with-docker-compose)
3. [Working with Local Files](#working-with-local-files)
4. [Environment Variables](#environment-variables)
5. [Custom Builds](#custom-builds)
6. [Note on Whisper Extra](#note-on-whisper-extra)

## Prerequisites

Before you begin, ensure you have the following installed on your system:

- Docker
- Docker Compose
- A `.env` file in the project root with necessary environment variables

## Running with Docker Compose

### Starting the Server

To start the server component:

```sh
docker-compose up server
```

This command will build the Docker image (if not already built) and start the server on port 8000.

### Using the CLI

To use the CLI component:

```sh
docker-compose run --rm cli [command] [arguments]
```

For example, to run the transcribe command:

```sh
docker-compose run --rm cli transcribe [source_file/url] [options]
```

## Working with Local Files

When using Docker, the container's filesystem is isolated from your host machine. To access local files, you need to "mount" them into the container using the `-v` or `--volume` flag.

### Files Within the Project Directory

For files within your project directory, you can mount the entire project directory:

```sh
docker-compose run --rm -v $(pwd):/app cli transcribe /app/test/testAssets/audio.mp3 [options]
```

This command:

- Mounts the current directory (`$(pwd)`) to `/app` in the container.
- Allows access to any file in your project directory.
- In this example, it transcribes the file at `/test/testAssets/audio.mp3` relative to your project root.

### Files Outside the Project Directory

For files outside your project directory, provide the full path:

```sh
docker-compose run --rm -v /path/to/external/directory:/external cli transcribe /external/audio.mp3 [options]
```

This command:

- Mounts `/path/to/external/directory` from your host to `/external` in the container.
- Allows access to files in that specific external directory.

### Multiple Mounts

You can use multiple `-v` flags to mount several directories:

```sh
docker-compose run --rm -v $(pwd):/app -v /path/to/external/directory:/external cli transcribe /external/audio.mp3 [options]
```

This mounts both your project directory and an external directory.

### Important Notes

1. Paths before the colon (`:`) are on your host machine; paths after are in the container.
2. Use absolute paths for directories outside your project.
3. Be cautious when mounting directories to avoid exposing sensitive data.
4. The working directory inside the container is set to `/app` in the Dockerfile, so paths are relative to that unless you specify absolute paths.

## Environment Variables

Both the server and CLI services use the `.env` file specified in the `docker-compose.yml`. Ensure this file contains all necessary variables for both components.

If you need to set or override environment variables for a specific run, you can use the `-e` flag:

```sh
docker-compose run --rm -e TRANSCRIPTION_SERVER_URL=http://host.docker.internal:8000 cli [command] [arguments]
```

## Custom Builds

If you need to modify the Docker setup:

1. Edit the `Dockerfile` or `docker-compose.yml` as needed.
2. Rebuild the services:
   ```sh
   docker-compose build
   ```

## Note on Whisper Extra

The default Docker setup does not include the Whisper extra. If you need Whisper for transcription:

1. Modify the `Dockerfile` to install Whisper.
2. Rebuild the Docker image:
   ```sh
   docker-compose build
   ```

Remember to adjust paths and environment variables as needed for your specific setup.
