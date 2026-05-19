# ============================================================ #
# DeepSeek OCR2 — Local OCR Engine with GPU/CUDA support
# ============================================================ #
# GPU: gunakan nvidia/cuda base image untuk CUDA support
# CPU: ganti ke python:3.12-slim untuk image lebih kecil

ARG CUDA_VERSION=12.4.1
ARG UBUNTU_VERSION=ubuntu22.04

# ── Base image ────────────────────────────────────────────── #
FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-${UBUNTU_VERSION} AS gpu-base

FROM python:3.12-slim AS cpu-base

# ── GPU build ─────────────────────────────────────────────── #
FROM gpu-base AS final

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN ln -sf /usr/bin/python3 /usr/bin/python

# ── CPU fallback ──────────────────────────────────────────── #
# FROM cpu-base AS final
# (uncomment above and comment gpu-base lines for CPU-only build)

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/outputs/markdown /app/outputs/json /app/outputs/images /app/uploads

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
