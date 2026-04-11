"""
BGE-M3 Embedder
==================
Tạo embedding vectors (Dense + Sparse) sử dụng model BAAI/bge-m3.

**Tại sao BGE-M3?** (ADR-002):
- Dense vector (1024 dims): Tốt cho câu hỏi NGỮ NGHĨA
  (VD: "quyền lợi thai sản là gì?")
- Sparse vector (lexical weights): Tốt cho câu hỏi EXACT-MATCH
  (VD: "Điều 141 Bộ luật Hình sự")
- Kết hợp qua RRF trong Qdrant → hybrid search chất lượng cao

**Yêu cầu phần cứng**:
- GPU (CUDA): Tốc độ tối ưu, ``use_fp16=True``
- CPU: Chậm hơn nhưng vẫn hoạt động, ``use_fp16=False``

Sử dụng::

    from src.ingestion.embedder import BGEEmbedder

    embedder = BGEEmbedder()
    result = embedder.embed(["Nội dung Khoản 1...", "Nội dung Khoản 2..."])
    dense_vectors = result["dense"]   # list[list[float]], shape [N, 1024]
    sparse_vectors = result["sparse"] # list[dict[int, float]]
"""

from __future__ import annotations

from src.core.config import get_settings
from src.core.exceptions import EmbeddingError
from src.core.logger import get_logger

logger = get_logger(__name__)


class BGEEmbedder:
    """
    Wrapper cho BAAI/bge-m3 embedding model.

    Hỗ trợ sinh đồng thời Dense vector (cho semantic search)
    và Sparse vector (cho lexical matching / BM25-style).

    Model được lazy-load lần đầu khi gọi ``embed()``,
    tránh tốn RAM/VRAM nếu chưa cần.

    Attributes:
        model_name: Tên model trên HuggingFace (mặc định "BAAI/bge-m3").
        batch_size: Số lượng text xử lý mỗi batch (mặc định 12).
        max_length: Độ dài tối đa của input text (mặc định 8192 tokens).
    """

    def __init__(
        self,
        model_name: str | None = None,
        batch_size: int | None = None,
        max_length: int | None = None,
    ) -> None:
        """
        Khởi tạo embedder (chưa load model).

        Args:
            model_name: Tên model. Mặc định đọc từ config.
            batch_size: Kích thước batch. Mặc định đọc từ config.
            max_length: Độ dài tối đa input. Mặc định đọc từ config.
        """
        settings = get_settings()
        self.model_name = model_name or settings.embedding_model
        self.batch_size = batch_size or settings.embedding_batch_size
        self.max_length = max_length or settings.embedding_max_length
        self._model = None  # Lazy loading

    def _load_model(self) -> None:
        """
        Load model BGE-M3 vào memory.

        Tự động detect GPU (CUDA) và sử dụng FP16 nếu có.
        Fallback sang CPU FP32 nếu không có GPU.

        Raises:
            EmbeddingError: Khi không thể load model.
        """
        try:
            import torch
            from FlagEmbedding import BGEM3FlagModel

            use_fp16 = torch.cuda.is_available()
            device = "cuda" if use_fp16 else "cpu"

            logger.info(
                "embedding_model_loading",
                model=self.model_name,
                device=device,
                fp16=use_fp16,
            )

            self._model = BGEM3FlagModel(
                self.model_name,
                use_fp16=use_fp16,
            )

            logger.info("embedding_model_loaded", model=self.model_name)

        except ImportError as e:
            raise EmbeddingError(
                "FlagEmbedding package not installed. "
                "Run: pip install FlagEmbedding",
                details={"error": str(e)},
            ) from e
        except Exception as e:
            raise EmbeddingError(
                f"Failed to load embedding model: {e}",
                details={"model": self.model_name, "error": str(e)},
            ) from e

    def embed(self, texts: list[str]) -> dict[str, list]:
        """
        Tạo Dense + Sparse embeddings cho danh sách texts.

        Args:
            texts: Danh sách văn bản cần embed.
                   Mỗi text là nội dung ``content`` của một chunk.

        Returns:
            dict với 2 keys:
            - ``"dense"``: list[list[float]] — Dense vectors, shape [N, 1024].
            - ``"sparse"``: list[dict[int, float]] — Sparse lexical weights.

        Raises:
            EmbeddingError: Khi quá trình embedding thất bại.

        Example::

            result = embedder.embed(["Nội dung khoản 1", "Nội dung khoản 2"])
            assert len(result["dense"]) == 2
            assert len(result["dense"][0]) == 1024
            assert isinstance(result["sparse"][0], dict)
        """
        if not texts:
            return {"dense": [], "sparse": []}

        # Lazy load model
        if self._model is None:
            self._load_model()

        try:
            logger.info(
                "embedding_started",
                num_texts=len(texts),
                batch_size=self.batch_size,
            )

            outputs = self._model.encode(
                texts,
                batch_size=self.batch_size,
                max_length=self.max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,  # Không cần ColBERT cho Phase 1
            )

            # Convert numpy arrays sang Python native types
            dense_vectors = outputs["dense_vecs"].tolist()
            sparse_vectors = [
                {int(k): float(v) for k, v in sparse.items()}
                for sparse in outputs["lexical_weights"]
            ]

            logger.info(
                "embedding_completed",
                num_texts=len(texts),
                dense_dim=len(dense_vectors[0]) if dense_vectors else 0,
            )

            return {
                "dense": dense_vectors,
                "sparse": sparse_vectors,
            }

        except Exception as e:
            logger.error("embedding_failed", error=str(e), num_texts=len(texts))
            raise EmbeddingError(
                f"Embedding failed: {e}",
                details={"num_texts": len(texts), "error": str(e)},
            ) from e
