# CareScribe model service — multi-stage build.
#
# Two image flavours from one file:
#
#   docker build -t carescribe-models ./models                  # core only (~300 MB)
#   docker build -t carescribe-models:full ./models \
#       --build-arg INSTALL_HEAVY=true                          # + torch/transformers (~3 GB)
#
# The core image boots every endpoint and serves the documented fallbacks, which
# is the right default for CI and for the first docker-compose up. The full image
# adds the real models.
#
# The service is INTERNAL ONLY: it listens on 0.0.0.0:9000 and must NOT appear in
# the public port map. Only the backend reaches it over the compose network.

# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — builder: compile wheels into a self-contained virtualenv
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

ARG INSTALL_HEAVY=false
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build tooling for any dependency without a prebuilt aarch64/x86_64 wheel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt requirements-models.txt ./

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# torch and torchvision come from the CPU-only index: the default CUDA wheels
# are several GB of GPU runtime this image cannot use. Rule 6 — GPU accelerates
# but never breaks.
RUN if [ "$INSTALL_HEAVY" = "true" ]; then \
        pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
        pip install transformers sentencepiece sentence-transformers faster-whisper gTTS xgboost shap; \
    fi

# ---------------------------------------------------------------------------
# Stage 2 — runtime: slim image, no compiler, non-root
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=9000 \
    HOST=0.0.0.0 \
    WEIGHTS_DIR=/app/weights \
    LOGS_DIR=/app/logs \
    REPORTS_DIR=/app/reports

# libgomp is required by torch/xgboost at runtime; libgl/libglib by Pillow.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY . /app

# Writable state. Mount a volume over /app/weights to supply trained checkpoints
# without rebuilding the image.
RUN mkdir -p /app/weights /app/logs /app/reports \
 && useradd --create-home --uid 10001 carescribe \
 && chown -R carescribe:carescribe /app

USER carescribe

EXPOSE 9000

# Uses the standard library so no curl/wget is needed in the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
port=os.getenv('PORT','9000'); \
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=4).status==200 else 1)"

CMD ["sh", "-c", "uvicorn main:app --host ${HOST} --port ${PORT} --workers 1"]
