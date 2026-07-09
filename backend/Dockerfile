FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    TRANSFORMERS_OFFLINE=0 \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/st \
    HF_HOME=/app/.cache/hf

# WeasyPrint needs Pango/Cairo/GLib + their dev headers to render PDFs.
# Slim image doesn't ship these — install once at build time so cold starts
# don't pay the cost.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
        libcairo2 libgdk-pixbuf-2.0-0 libffi8 \
        fonts-dejavu-core fonts-liberation \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Pre-download the BGE model so first request isn't slow
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
