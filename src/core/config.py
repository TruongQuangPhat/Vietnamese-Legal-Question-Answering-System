"""
VnLaw-QA Configuration
=======================
Quản lý toàn bộ cấu hình ứng dụng thông qua Pydantic Settings.
Đọc biến môi trường từ file .env, KHÔNG hardcode bất kỳ secret nào.

Sử dụng::

    from src.core.config import get_settings
    settings = get_settings()
    print(settings.qdrant_url)
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Đường dẫn gốc của project (thư mục chứa pyproject.toml)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """
    Cấu hình trung tâm cho toàn bộ ứng dụng VnLaw-QA.

    Mọi giá trị được đọc từ biến môi trường hoặc file .env.
    Các giá trị mặc định đảm bảo ứng dụng chạy được trong môi trường dev
    mà không cần cấu hình phức tạp.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o"

    # --- Vector DB (Qdrant) ---
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = "vnlaw_legal_docs"

    # --- Graph DB (Neo4j) ---
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")

    # --- Cache (Redis) ---
    redis_url: str = "redis://localhost:6379"
    redis_password: SecretStr = SecretStr("")

    # --- Embedding ---
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = 12
    embedding_max_length: int = 8192

    # --- Crawl ---
    crawl_rate_limit: float = 2.0
    crawl_max_concurrent: int = 3

    # --- App ---
    log_level: str = "INFO"
    confidence_threshold: float = 0.75
    max_context_docs: int = 5
    llm_timeout_seconds: int = 30


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Trả về singleton Settings instance.

    Sử dụng lru_cache để đảm bảo chỉ khởi tạo Settings một lần duy nhất,
    tránh đọc lại file .env mỗi khi gọi.

    Returns:
        Settings: Instance cấu hình ứng dụng.
    """
    return Settings()


def load_yaml_config(config_name: str) -> dict[str, Any]:
    """
    Đọc file YAML config từ thư mục ``config/``.

    Args:
        config_name: Tên file config (VD: "chunking.yml", "retrieval.yml").

    Returns:
        dict: Nội dung config đã parse.

    Raises:
        FileNotFoundError: Nếu file config không tồn tại.
    """
    config_path = PROJECT_ROOT / "config" / config_name
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
