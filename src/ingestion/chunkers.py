"""
Parent-Child Document Chunker
================================
Chia văn bản pháp luật thành chunks theo chiến lược Parent-Child (ADR-003).

**Chiến lược** (từ context.md):
- Index theo Khoản/Điểm (child) → precision cao hơn cho vector search
  (embedding vector tập trung ngữ nghĩa tốt hơn trên đoạn ngắn).
- Trả về toàn bộ Điều (parent) cho LLM → tránh hallucination
  (LLM cần context đầy đủ để hiểu các quy phạm liên quan).

**Đơn vị chunk**:
- ``content`` (child): Nội dung 1 Khoản hoặc 1 Điểm
- ``parent_content`` (parent): Toàn bộ nội dung Điều chứa chunk đó

**Edge cases**:
- Điều không có Khoản → Toàn bộ Điều là 1 chunk duy nhất
- Khoản không có Điểm → Khoản là chunk, không tách thêm
- Khoản có Điểm → Mỗi Điểm là 1 chunk riêng

Sử dụng::

    from src.ingestion.chunkers import ParentChildChunker

    chunker = ParentChildChunker()
    chunks = chunker.chunk_articles(articles, law_metadata, source_info)
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from src.core.logger import get_logger
from src.ingestion.parsers.legal_parser import ArticleNode
from src.ingestion.schemas import (
    Hierarchy,
    LawMetadata,
    LegalChunkNode,
    SourceInfo,
)

logger = get_logger(__name__)


class ParentChildChunker:
    """
    Chia ArticleNode thành LegalChunkNode theo chiến lược Parent-Child.

    Workflow::

        list[ArticleNode]
        → chunk_articles()
        → list[LegalChunkNode]  # Mỗi chunk đã validate qua Pydantic schema

    Mỗi chunk đầu ra tuân thủ **tuyệt đối** schema ``LegalChunkNode``
    (rules.md §3.1), bao gồm:
    - ``chunk_id``: UUID4 unique
    - ``hierarchy``: Vị trí phân cấp đầy đủ
    - ``content``: Nội dung child (cho vector search)
    - ``parent_content``: Nội dung Điều cha (cho LLM context)
    """

    def chunk_articles(
        self,
        articles: list[ArticleNode],
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> list[LegalChunkNode]:
        """
        Chia toàn bộ danh sách ArticleNode thành LegalChunkNode.

        Args:
            articles: Danh sách Điều đã parse từ VietnamLegalParser.
            law_metadata: Metadata của văn bản luật (law_id, law_name, ...).
            source_info: Thông tin nguồn crawl (url, timestamp).

        Returns:
            list[LegalChunkNode]: Danh sách chunks đã validate,
                                  sẵn sàng để embed và ingest vào Qdrant.
        """
        all_chunks: list[LegalChunkNode] = []

        for article in articles:
            chunks = self._chunk_single_article(article, law_metadata, source_info)
            all_chunks.extend(chunks)

        logger.info(
            "chunking_completed",
            total_articles=len(articles),
            total_chunks=len(all_chunks),
            law_id=law_metadata.law_id,
        )
        return all_chunks

    def _chunk_single_article(
        self,
        article: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> list[LegalChunkNode]:
        """
        Chia một Điều thành các chunk con.

        Logic phân nhánh:
        1. Điều KHÔNG có Khoản → 1 chunk duy nhất (Điều = cả parent & child)
        2. Khoản KHÔNG có Điểm → 1 chunk per Khoản
        3. Khoản CÓ Điểm → 1 chunk per Điểm (granular hơn)

        Args:
            article: ArticleNode đã parse.
            law_metadata: Metadata luật.
            source_info: Thông tin nguồn.

        Returns:
            list[LegalChunkNode]: Chunks từ Điều này.
        """
        chunks: list[LegalChunkNode] = []
        parent_content = article.full_content

        # Case 1: Điều không có Khoản → chunk toàn bộ Điều
        if not article.clauses:
            chunk = LegalChunkNode(
                chunk_id=uuid4(),
                law_metadata=law_metadata,
                hierarchy=Hierarchy(
                    phan=article.phan,
                    chuong=article.chuong,
                    muc=article.muc,
                    dieu=f"Điều {article.dieu_number}",
                    dieu_title=article.dieu_title,
                    khoan=None,
                    diem=None,
                ),
                content=parent_content,
                parent_content=parent_content,
                cross_references=article.cross_references,
                source_info=source_info,
            )
            chunks.append(chunk)
            return chunks

        # Case 2 & 3: Duyệt từng Khoản
        for clause in article.clauses:
            if clause.points:
                # Case 3: Khoản có Điểm → mỗi Điểm là 1 chunk
                for point in clause.points:
                    chunk = LegalChunkNode(
                        chunk_id=uuid4(),
                        law_metadata=law_metadata,
                        hierarchy=Hierarchy(
                            phan=article.phan,
                            chuong=article.chuong,
                            muc=article.muc,
                            dieu=f"Điều {article.dieu_number}",
                            dieu_title=article.dieu_title,
                            khoan=f"Khoản {clause.number}",
                            diem=f"Điểm {point.letter}",
                        ),
                        content=point.content,
                        parent_content=parent_content,
                        cross_references=article.cross_references,
                        source_info=source_info,
                    )
                    chunks.append(chunk)
            else:
                # Case 2: Khoản không có Điểm → Khoản là 1 chunk
                chunk = LegalChunkNode(
                    chunk_id=uuid4(),
                    law_metadata=law_metadata,
                    hierarchy=Hierarchy(
                        phan=article.phan,
                        chuong=article.chuong,
                        muc=article.muc,
                        dieu=f"Điều {article.dieu_number}",
                        dieu_title=article.dieu_title,
                        khoan=f"Khoản {clause.number}",
                        diem=None,
                    ),
                    content=clause.content,
                    parent_content=parent_content,
                    cross_references=article.cross_references,
                    source_info=source_info,
                )
                chunks.append(chunk)

        return chunks


def build_law_metadata(
    law_id: str,
    law_name: str,
    year: int,
    effective_date: str | date | None = None,
    domain_tags: list[str] | None = None,
    status: str = "active",
) -> LawMetadata:
    """
    Helper function tạo LawMetadata với interface đơn giản.

    Args:
        law_id: Mã ID chuẩn (VD: "BLDS_2015").
        law_name: Tên đầy đủ.
        year: Năm ban hành.
        effective_date: Ngày hiệu lực (str "YYYY-MM-DD" hoặc date object).
        domain_tags: Nhãn lĩnh vực.
        status: Trạng thái ("active", "inactive", "draft").

    Returns:
        LawMetadata: Object metadata đã validate.
    """
    eff_date: date | None = None
    if isinstance(effective_date, str):
        eff_date = date.fromisoformat(effective_date)
    elif isinstance(effective_date, date):
        eff_date = effective_date

    return LawMetadata(
        law_id=law_id,
        law_name=law_name,
        year=year,
        effective_date=eff_date,
        expiry_date=None,
        status=status,  # type: ignore[arg-type]
        domain_tags=domain_tags or [],
    )
