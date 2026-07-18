# syntax=docker/dockerfile:1.7

FROM python:3.11-slim AS embedding-model

ARG EMBEDDING_MODEL_ID=BAAI/bge-m3
ARG EMBEDDING_MODEL_REVISION=5617a9f61b028005a4858fdac845db406aefb181
ARG EMBEDDING_MODEL_PATH=/models/embedding/bge-m3

ENV EMBEDDING_MODEL_ID=${EMBEDDING_MODEL_ID} \
    EMBEDDING_MODEL_REVISION=${EMBEDDING_MODEL_REVISION} \
    EMBEDDING_MODEL_PATH=${EMBEDDING_MODEL_PATH}

RUN python -m pip install --no-cache-dir "huggingface_hub==1.18.0"

RUN python - <<'PY'
from __future__ import annotations

import os
from pathlib import Path

from huggingface_hub import snapshot_download

model_id = os.environ.get("EMBEDDING_MODEL_ID", "BAAI/bge-m3")
revision = os.environ.get(
    "EMBEDDING_MODEL_REVISION",
    "5617a9f61b028005a4858fdac845db406aefb181",
)
model_path = Path(os.environ.get("EMBEDDING_MODEL_PATH", "/models/embedding/bge-m3"))
model_path.mkdir(parents=True, exist_ok=True)
snapshot_download(
    repo_id=model_id,
    revision=revision,
    local_dir=model_path,
    local_dir_use_symlinks=False,
    ignore_patterns=["*.jpg", "*.webp", "*.onnx"],
)

required_all = ("config.json",)
required_any_groups = (
    ("pytorch_model.bin", "model.safetensors"),
    ("tokenizer.json", "sentencepiece.bpe.model"),
)
missing = [name for name in required_all if not (model_path / name).is_file()]
missing.extend(
    " or ".join(group) for group in required_any_groups if not any((model_path / name).is_file() for name in group)
)
if missing:
    raise SystemExit("Downloaded embedding model snapshot is incomplete.")
PY

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
    && uv cache clean \
    && rm -rf /root/.cache/pip /tmp/*

COPY src ./src
COPY configs ./configs

RUN mkdir -p /home/data

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS production-with-chunks

COPY --from=legal_chunks legal_chunks.jsonl /home/data/legal_chunks.jsonl
COPY --from=embedding-model /models/embedding/bge-m3 /models/embedding/bge-m3

ENV EMBEDDING_MODEL_PATH=/models/embedding/bge-m3 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1

FROM runtime AS final
