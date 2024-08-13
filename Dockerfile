# Use Python 3.10 as the base image
FROM python:3.10

# Set the working directory
WORKDIR /app

# Copy requirements file first to leverage caching
COPY requirements.txt /app/requirements.txt

# Install dependencies
# This layer is cached if requirements don't change
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the application
# Done after installing deps to preserve caching
COPY . /app

# Install the package itself
# Includes the tstbtc-server entry point
RUN pip install --no-cache-dir .
# To include Whisper support, uncomment the following line:
# RUN pip install --no-cache-dir .[whisper]