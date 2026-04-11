"""
Qdrant Vector Store Wrapper
==============================
Wrapper bất đồng bộ cho Qdrant vector database, hỗ trợ Hybrid Search
kết hợp Dense (semantic) + Sparse (lexical) qua Reciprocal Rank Fusion.

**Cấu hình collection** (ADR-002):
- Dense vector: 1024 dims (BAAI/bge-m3), COSINE distance
- Sparse vector: Lexical weights từ BGE-M3, DOT product
- Fusion: RRF (Reciprocal Rank Fusion) — robust, không cần tune weights

**Payload structure** (mỗi point trong Qdrant):
- ``chunk_id``, ``law_id``, ``law_name``, ``year``, ``status``
- ``hierarchy``: {phan, chuong, muc, dieu, dieu_title, khoan, diem}
- ``content``, ``parent_content``
- ``cross_references``, ``source_url``, ``crawled_at``
- ``domain_tags``, ``effective_date``

Sử dụng::

    from src.retrieval.vector_store import QdrantVectorStore

    store = QdrantVectorStore()
    await store.setup_collection()
    await store.upsert_chunks(chunks, dense_vectors, sparse_vectors)
    results = await store.hybrid_search(query_dense, query_sparse, top_k=20)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    Fusion,
    FusionQuery,
    HnswConfigDiff,
    NamedSparseVector,
    NamedVector,
    PointStruct,
    Prefetch,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.core.config import get_settings
from src.core.exceptions import VectorStoreError
from src.core.logger import get_logger

if TYPE_CHECKING:
    from src.ingestion.schemas import LegalChunkNode

logger = get_logger(__name__)


class QdrantVectorStore:
    """
    Wrapper bất đồng bộ cho Qdrant, chuyên dụng cho dữ liệu pháp luật.

    Hỗ trợ:
    - Tạo collection với Dense + Sparse vector configs
    - Batch upsert chunks với full metadata payload
    - Hybrid search (RRF fusion) cho retrieval chất lượng cao
    - Đếm số points theo law_id (verification)

    Attributes:
        collection_name: Tên Qdrant collection.
        client: AsyncQdrantClient instance.
    """

    # Kích thước dense vector (BAAI/bge-m3 output)
    DENSE_VECTOR_SIZE: int = 1024

    def __init__(
        self,
        collection_name: str | None = None,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ) -> None:
        """
        Khởi tạo Qdrant client.

        Args:
            collection_name: Tên collection. Mặc định đọc từ config.
            qdrant_url: URL Qdrant server. Mặc định đọc từ config.
            qdrant_api_key: API key (nếu có). Mặc định đọc từ config.
        """
        settings = get_settings()
        self.collection_name = collection_name or settings.qdrant_collection

        api_key = qdrant_api_key or settings.qdrant_api_key.get_secret_value()

        self.client = AsyncQdrantClient(
            url=qdrant_url or settings.qdrant_url,
            api_key=api_key if api_key else None,
        )

    async def setup_collection(self) -> None:
        """
        Tạo Qdrant collection với cấu hình Hybrid Search.

        Cấu hình:
        - Dense vector ``"dense"``: 1024 dims, COSINE, HNSW(m=16, ef=100)
        - Sparse vector ``"sparse"``: Inverted index, in-memory

        Nếu collection đã tồn tại → skip (không xóa dữ liệu cũ).

        Raises:
            VectorStoreError: Khi không thể tạo collection.
        """
        try:
            # Kiểm tra collection đã tồn tại chưa
            collections = await self.client.get_collections()
            existing = [c.name for c in collections.collections]

            if self.collection_name in existing:
                logger.info(
                    "collection_exists",
                    collection=self.collection_name,
                )
                return

            # Tạo collection mới
            await self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=self.DENSE_VECTOR_SIZE,
                        distance=Distance.COSINE,
                        hnsw_config=HnswConfigDiff(m=16, ef_construct=100),
                    ),
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(on_disk=False),
                    ),
                },
            )

            logger.info(
                "collection_created",
                collection=self.collection_name,
                dense_size=self.DENSE_VECTOR_SIZE,
            )

        except Exception as e:
            logger.error(
                "collection_setup_failed",
                collection=self.collection_name,
                error=str(e),
            )
            raise VectorStoreError(
                f"Failed to setup collection: {e}",
                details={"collection": self.collection_name},
            ) from e

    async def upsert_chunks(
        self,
        chunks: list[LegalChunkNode],
        dense_vectors: list[list[float]],
        sparse_vectors: list[dict[int, float]],
        batch_size: int = 100,
    ) -> int:
        """
        Batch upsert chunks vào Qdrant với full metadata payload.

        Args:
            chunks: Danh sách LegalChunkNode đã validate.
            dense_vectors: Dense embeddings tương ứng, shape [N, 1024].
            sparse_vectors: Sparse lexical weights tương ứng.
            batch_size: Số points upsert mỗi batch (mặc định 100).

        Returns:
            int: Tổng số points đã upsert thành công.

        Raises:
            VectorStoreError: Khi upsert thất bại.
            ValueError: Khi số lượng chunks không khớp với vectors.
        """
        if len(chunks) != len(dense_vectors) or len(chunks) != len(sparse_vectors):
            raise ValueError(
                f"Mismatch: {len(chunks)} chunks, "
                f"{len(dense_vectors)} dense, {len(sparse_vectors)} sparse"
            )

        total_upserted = 0

        try:
            # Tạo PointStruct cho mỗi chunk
            points: list[PointStruct] = []
            for chunk, dense, sparse in zip(
                chunks, dense_vectors, sparse_vectors, strict=True
            ):
                payload = self._chunk_to_payload(chunk)

                point = PointStruct(
                    id=str(chunk.chunk_id),
                    vector={
                        "dense": dense,
                        "sparse": SparseVector(
                            indices=list(sparse.keys()),
                            values=list(sparse.values()),
                        ),
                    },
                    payload=payload,
                )
                points.append(point)

            # Batch upsert
            for i in range(0, len(points), batch_size):
                batch = points[i : i + batch_size]
                await self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch,
                )
                total_upserted += len(batch)
                logger.info(
                    "batch_upserted",
                    batch_number=i // batch_size + 1,
                    batch_size=len(batch),
                    total=total_upserted,
                )

            logger.info(
                "upsert_completed",
                total_points=total_upserted,
                collection=self.collection_name,
            )
            return total_upserted

        except Exception as e:
            logger.error(
                "upsert_failed",
                error=str(e),
                upserted_so_far=total_upserted,
            )
            raise VectorStoreError(
                f"Upsert failed: {e}",
                details={"upserted": total_upserted, "total": len(chunks)},
            ) from e

    async def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: dict[int, float],
        top_k: int = 20,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Hybrid search kết hợp Dense + Sparse qua RRF fusion.

        Pipeline (ADR-002):
        1. Prefetch top_k*2 từ Dense search (semantic)
        2. Prefetch top_k*2 từ Sparse search (lexical)
        3. Fuse bằng RRF (Reciprocal Rank Fusion)
        4. Trả về top_k kết quả cuối cùng

        Args:
            query_dense: Dense embedding vector của query, shape [1024].
            query_sparse: Sparse lexical weights của query.
            top_k: Số kết quả trả về (mặc định 20).
            filter_conditions: Filter Qdrant (VD: {"law_id": "BLDS_2015"}).

        Returns:
            list[dict]: Danh sách payloads kết quả, mỗi dict chứa toàn bộ
                       metadata, hierarchy, content, parent_content.

        Raises:
            VectorStoreError: Khi search thất bại.
        """
        try:
            results = await self.client.query_points(
                collection_name=self.collection_name,
                prefetch=[
                    Prefetch(
                        query=NamedVector(name="dense", vector=query_dense),
                        limit=top_k * 2,
                    ),
                    Prefetch(
                        query=NamedSparseVector(
                            name="sparse",
                            vector=SparseVector(
                                indices=list(query_sparse.keys()),
                                values=list(query_sparse.values()),
                            ),
                        ),
                        limit=top_k * 2,
                    ),
                ],
                query=FusionQuery(fusion=Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )

            payloads = [
                {**hit.payload, "score": hit.score}
                for hit in results.points
                if hit.payload
            ]

            logger.info(
                "hybrid_search_completed",
                results_count=len(payloads),
                top_k=top_k,
            )
            return payloads

        except Exception as e:
            logger.error("hybrid_search_failed", error=str(e))
            raise VectorStoreError(
                f"Hybrid search failed: {e}",
            ) from e

    async def count_by_law_id(self, law_id: str) -> int:
        """
        Đếm số points trong collection thuộc một law_id cụ thể.

        Dùng để verify sau khi ingest:
        so sánh với số Điều mong đợi trong luật gốc.

        Args:
            law_id: Mã ID luật cần đếm (VD: "BLDS_2015").

        Returns:
            int: Số lượng points thuộc law_id.
        """
        try:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            result = await self.client.count(
                collection_name=self.collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="law_id",
                            match=MatchValue(value=law_id),
                        ),
                    ],
                ),
                exact=True,
            )
            return result.count

        except Exception as e:
            logger.error("count_failed", law_id=law_id, error=str(e))
            raise VectorStoreError(
                f"Count failed for {law_id}: {e}",
            ) from e

    @staticmethod
    def _chunk_to_payload(chunk: LegalChunkNode) -> dict[str, Any]:
        """
        Chuyển đổi LegalChunkNode thành Qdrant payload dict.

        Flatten nested Pydantic objects thành dict phẳng phù hợp
        cho Qdrant indexing và filtering.

        Args:
            chunk: LegalChunkNode đã validate.

        Returns:
            dict: Payload sẵn sàng cho Qdrant upsert.
        """
        return {
            # Identifiers
            "chunk_id": str(chunk.chunk_id),
            "law_id": chunk.law_metadata.law_id,
            "law_name": chunk.law_metadata.law_name,
            "year": chunk.law_metadata.year,
            "status": chunk.law_metadata.status,
            "domain_tags": chunk.law_metadata.domain_tags,
            "effective_date": (
                chunk.law_metadata.effective_date.isoformat()
                if chunk.law_metadata.effective_date
                else None
            ),
            # Hierarchy (flatten)
            "phan": chunk.hierarchy.phan,
            "chuong": chunk.hierarchy.chuong,
            "muc": chunk.hierarchy.muc,
            "dieu": chunk.hierarchy.dieu,
            "dieu_title": chunk.hierarchy.dieu_title,
            "khoan": chunk.hierarchy.khoan,
            "diem": chunk.hierarchy.diem,
            # Content
            "content": chunk.content,
            "parent_content": chunk.parent_content,
            # Cross references
            "cross_references": chunk.cross_references,
            # Source
            "source_url": str(chunk.source_info.url),
            "crawled_at": chunk.source_info.crawled_at.isoformat(),
        }
