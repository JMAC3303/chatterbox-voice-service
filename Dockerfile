# City Center Voice Service (Chatterbox) — GPU image.
# Base: CUDA 12.1 runtime on Ubuntu 22.04 (matches the torch cu121 wheels).
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-venv \
    ffmpeg libsndfile1 git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

# Install PyTorch (CUDA 12.1) first so it isn't overridden by a CPU build.
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121

COPY requirements.txt .
RUN python3 -m pip install -r requirements.txt

COPY app ./app

# Model weights download on first startup (warmup) into the HF cache. Mount a
# volume at /root/.cache/huggingface to persist them across restarts.
EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
