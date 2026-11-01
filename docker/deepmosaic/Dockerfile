# DeepMosaic worker container.
# Owns torch + the DeepMosaics submodule + model weights, exposing a small
# HTTP API (server.py) that the main Social-Hunt app calls over the internal
# docker network via DEEPMOSAIC_URL. This keeps the vulnerable/heavy torch
# stack OUT of the main app container.
FROM python:3.11-slim

# System deps for OpenCV/torch/DeepMosaics
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    g++ \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    wget \
    unzip \
    unrar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps: torch CPU build + the wrapper server deps + DeepMosaics deps.
# DeepMosaics runs in its own container, but isolation is not a substitute for
# patching dependencies; use security-fixed Torch and image libraries here.
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    "torch>=2.10.0" "torchvision>=0.25.0" \
    "numpy<2.0" \
    "opencv-python-headless>=4.8.1.78" \
    ffmpeg-python \
    tqdm \
    "pillow>=12.3.0" \
    fastapi \
    "uvicorn[standard]"

# The DeepMosaics source is copied in from the host submodule.
# (git submodule update --init --recursive DeepMosaics must be run first.)
COPY DeepMosaics/ /app/DeepMosaics/

# Copy the HTTP wrapper.
COPY docker/deepmosaic/server.py /app/server.py

# Download model weights using the project's own downloader (non-interactive).
# Piping "n" skips the optional RAR extraction prompt; single-file models are
# still fetched. If clean_face_HD.pth is absent, clean mode falls back to the
# other clean models the wrapper looks for.
COPY download_deepmosaic_models.py /app/download_deepmosaic_models.py
RUN cd /app/DeepMosaics && printf 'n\nn\n' | python /app/download_deepmosaic_models.py || \
    echo "[deepmosaic-worker] model download partially failed; some modes may be unavailable"

ENV DEEPMOSAIC_DIR=/app/DeepMosaics \
    DEEPMOSAIC_RESULTS_DIR=/tmp/deepmosaic_results \
    DEEPMOSAIC_TEMP_DIR=/tmp/deepmosaic_temp

EXPOSE 8081

CMD ["python", "/app/server.py"]
