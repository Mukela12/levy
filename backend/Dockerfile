FROM python:3.12-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONUNBUFFERED=1 \
    TRANSFORMERS_OFFLINE=0 \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/st \
    HF_HOME=/app/.cache/hf

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Pre-download the BGE model so first request isn't slow
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
