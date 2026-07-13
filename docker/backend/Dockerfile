# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_TORCH_BACKEND=cpu \
    LEGAL_QA_SERVICE_MODE=fake \
    LEGAL_QA_CHUNKS_PATH=/home/data/legal_chunks.jsonl \
    PORT=8000 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN python -m pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./

RUN uv sync \
    --frozen \
    --no-dev \
    --extra qdrant \
    --extra embedding \
    --no-install-project \
    --no-cache \
    --torch-backend cpu \
    && uv cache clean \
    && rm -rf /root/.cache/pip /tmp/*

COPY src ./src
COPY configs ./configs

RUN mkdir -p /home/data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS production-with-chunks

COPY --from=legal_chunks legal_chunks.jsonl /home/data/legal_chunks.jsonl

FROM runtime AS final
