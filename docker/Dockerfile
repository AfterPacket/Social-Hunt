# Use a slim Python 3.11 base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SOCIAL_HUNT_JOBS_DIR=/app/data/jobs \
    SOCIAL_HUNT_SETTINGS_PATH=/app/data/settings.json

# Set work directory
WORKDIR /app

# Install system dependencies required for build and face recognition (dlib)
# We need cmake, g++, and other build tools to compile dlib from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    g++ \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-python-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements-docker.txt .

# Install Python dependencies
# Note: dlib and face_recognition can take a while to compile
RUN pip install --no-cache-dir --upgrade pip setuptools && \
    pip install --no-cache-dir -r requirements-docker.txt

# Copy the rest of the application
COPY . .

# Create necessary directories and ensure they are writable
RUN mkdir -p data/jobs plugins/providers temp web/temp_uploads && \
    chmod -R 777 data plugins temp web/temp_uploads

# Expose the application port
EXPOSE 8000

# Start the application using uvicorn
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
