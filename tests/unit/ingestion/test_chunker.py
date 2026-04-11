"""
Unit Tests — Parent-Child Chunker
====================================
Test suite cho ParentChildChunker.

Bao gồm tests cho:
1. Chunk generation từ ArticleNode
2. Schema compliance (tất cả fields bắt buộc)
3. Edge cases: Điều không có Khoản, Khoản không có Điểm
4. UUID uniqueness
5. Parent-child relationship
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.ingestion.chunkers import ParentChildChunker, build_law_metadata
from src.ingestion.parsers.legal_parser import (
    ArticleNode,
    ClauseNode,
    PointNode,
    VietnamLegalParser,
)
from src.ingestion.schemas import LawMetadata, LegalChunkNode, SourceInfo

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def chunker() -> ParentChildChunker:
    """Chunker instance."""
    return ParentChildChunker()


@pytest.fixture
def law_metadata() -> LawMetadata:
    """Metadata mẫu cho Bộ luật Dân sự."""
    return build_law_metadata(
        law_id="BLDS_2015",
        law_name="Bộ luật Dân sự 2015",
        year=2015,
        effective_date="2017-01-01",
        domain_tags=["dân sự", "hợp đồng", "tài sản"],
    )


@pytest.fixture
def source_info() -> SourceInfo:
    """Source info mẫu."""
    return SourceInfo(
        url="https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx",  # type: ignore[arg-type]
        crawled_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def article_without_clauses() -> ArticleNode:
    """Điều không có Khoản (toàn bộ Điều là nội dung liền)."""
    return ArticleNode(
        dieu_number="1",
        dieu_title="Phạm vi điều chỉnh",
        full_content="Điều 1. Phạm vi điều chỉnh\nBộ luật này quy định địa vị pháp lý.",
        clauses=[],
        phan="Phần thứ nhất",
        chuong="Chương I NHỮNG QUY ĐỊNH CHUNG",
        muc=None,
    )


@pytest.fixture
def article_with_clauses_only() -> ArticleNode:
    """Điều có Khoản nhưng không có Điểm."""
    return ArticleNode(
        dieu_number="2",
        dieu_title="Công nhận quyền dân sự",
        full_content=(
            "Điều 2. Công nhận quyền dân sự\n"
            "1. Các quyền dân sự được công nhận.\n"
            "2. Quyền dân sự chỉ có thể bị hạn chế."
        ),
        clauses=[
            ClauseNode(number="1", content="1. Các quyền dân sự được công nhận.", points=[]),
            ClauseNode(number="2", content="2. Quyền dân sự chỉ có thể bị hạn chế.", points=[]),
        ],
        phan="Phần thứ nhất",
        chuong="Chương I NHỮNG QUY ĐỊNH CHUNG",
        muc=None,
    )


@pytest.fixture
def article_with_points() -> ArticleNode:
    """Điều có Khoản + Điểm."""
    return ArticleNode(
        dieu_number="17",
        dieu_title="Thu hồi đất",
        full_content=(
            "Điều 17. Thu hồi đất\n"
            "1. Nhà nước thu hồi đất:\n"
            "a) Vì mục đích quốc phòng;\n"
            "b) Vì phát triển kinh tế;\n"
            "2. Trưng dụng đất theo Điều 82."
        ),
        clauses=[
            ClauseNode(
                number="1",
                content="1. Nhà nước thu hồi đất:\na) Vì mục đích quốc phòng;\nb) Vì phát triển kinh tế;",
                points=[
                    PointNode(letter="a", content="a) Vì mục đích quốc phòng;"),
                    PointNode(letter="b", content="b) Vì phát triển kinh tế;"),
                ],
            ),
            ClauseNode(
                number="2",
                content="2. Trưng dụng đất theo Điều 82.",
                points=[],
            ),
        ],
        phan=None,
        chuong="Chương II",
        muc="Mục 1",
        cross_references=["Điều 82"],
    )


# =============================================================================
# TESTS
# =============================================================================

class TestParentChildChunker:
    """Tests cho ParentChildChunker."""

    # --- Case 1: Điều không có Khoản ---

    def test_article_without_clauses_single_chunk(
        self,
        chunker: ParentChildChunker,
        article_without_clauses: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Điều không có Khoản → sinh đúng 1 chunk."""
        chunks = chunker.chunk_articles(
            [article_without_clauses], law_metadata, source_info
        )
        assert len(chunks) == 1

    def test_article_without_clauses_content_equals_parent(
        self,
        chunker: ParentChildChunker,
        article_without_clauses: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Khi không có Khoản, content == parent_content."""
        chunks = chunker.chunk_articles(
            [article_without_clauses], law_metadata, source_info
        )
        assert chunks[0].content == chunks[0].parent_content

    # --- Case 2: Khoản không có Điểm ---

    def test_clauses_only_chunk_count(
        self,
        chunker: ParentChildChunker,
        article_with_clauses_only: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """2 Khoản không có Điểm → sinh đúng 2 chunks."""
        chunks = chunker.chunk_articles(
            [article_with_clauses_only], law_metadata, source_info
        )
        assert len(chunks) == 2

    def test_clauses_only_hierarchy(
        self,
        chunker: ParentChildChunker,
        article_with_clauses_only: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Mỗi chunk phải có Khoản trong hierarchy."""
        chunks = chunker.chunk_articles(
            [article_with_clauses_only], law_metadata, source_info
        )
        assert chunks[0].hierarchy.khoan == "Khoản 1"
        assert chunks[1].hierarchy.khoan == "Khoản 2"
        # Không có Điểm
        assert chunks[0].hierarchy.diem is None

    # --- Case 3: Khoản có Điểm ---

    def test_article_with_points_chunk_count(
        self,
        chunker: ParentChildChunker,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Khoản 1 (2 Điểm) + Khoản 2 (0 Điểm) → 3 chunks."""
        chunks = chunker.chunk_articles(
            [article_with_points], law_metadata, source_info
        )
        assert len(chunks) == 3

    def test_article_with_points_hierarchy(
        self,
        chunker: ParentChildChunker,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Điểm chunks phải có cả Khoản và Điểm trong hierarchy."""
        chunks = chunker.chunk_articles(
            [article_with_points], law_metadata, source_info
        )
        # Chunk 0: Khoản 1, Điểm a
        assert chunks[0].hierarchy.khoan == "Khoản 1"
        assert chunks[0].hierarchy.diem == "Điểm a"
        # Chunk 1: Khoản 1, Điểm b
        assert chunks[1].hierarchy.khoan == "Khoản 1"
        assert chunks[1].hierarchy.diem == "Điểm b"
        # Chunk 2: Khoản 2, no Điểm
        assert chunks[2].hierarchy.khoan == "Khoản 2"
        assert chunks[2].hierarchy.diem is None

    # --- Schema compliance ---

    def test_all_chunks_have_uuid(
        self,
        chunker: ParentChildChunker,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Mọi chunk phải có chunk_id là UUID."""
        chunks = chunker.chunk_articles(
            [article_with_points], law_metadata, source_info
        )
        for chunk in chunks:
            assert chunk.chunk_id is not None

    def test_uuid_uniqueness(
        self,
        chunker: ParentChildChunker,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Mọi chunk_id phải unique."""
        chunks = chunker.chunk_articles(
            [article_with_points], law_metadata, source_info
        )
        ids = [str(c.chunk_id) for c in chunks]
        assert len(ids) == len(set(ids))

    def test_all_chunks_have_law_metadata(
        self,
        chunker: ParentChildChunker,
        article_with_clauses_only: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Mọi chunk phải có law_metadata đầy đủ."""
        chunks = chunker.chunk_articles(
            [article_with_clauses_only], law_metadata, source_info
        )
        for chunk in chunks:
            assert chunk.law_metadata.law_id == "BLDS_2015"
            assert chunk.law_metadata.law_name == "Bộ luật Dân sự 2015"
            assert chunk.law_metadata.year == 2015

    def test_parent_content_contains_full_article(
        self,
        chunker: ParentChildChunker,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """parent_content phải chứa toàn bộ nội dung Điều cha."""
        chunks = chunker.chunk_articles(
            [article_with_points], law_metadata, source_info
        )
        for chunk in chunks:
            assert "Điều 17. Thu hồi đất" in chunk.parent_content

    def test_chunks_are_pydantic_validated(
        self,
        chunker: ParentChildChunker,
        article_with_clauses_only: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Mọi chunk phải là LegalChunkNode instance (đã validate Pydantic)."""
        chunks = chunker.chunk_articles(
            [article_with_clauses_only], law_metadata, source_info
        )
        for chunk in chunks:
            assert isinstance(chunk, LegalChunkNode)

    # --- Cross references ---

    def test_cross_references_propagated(
        self,
        chunker: ParentChildChunker,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Cross references từ ArticleNode phải được copy vào mỗi chunk."""
        chunks = chunker.chunk_articles(
            [article_with_points], law_metadata, source_info
        )
        for chunk in chunks:
            assert "Điều 82" in chunk.cross_references

    # --- Multiple articles ---

    def test_multiple_articles(
        self,
        chunker: ParentChildChunker,
        article_without_clauses: ArticleNode,
        article_with_clauses_only: ArticleNode,
        article_with_points: ArticleNode,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Nhiều Điều cùng lúc → tổng chunks đúng."""
        articles = [
            article_without_clauses,   # → 1 chunk
            article_with_clauses_only, # → 2 chunks
            article_with_points,       # → 3 chunks
        ]
        chunks = chunker.chunk_articles(articles, law_metadata, source_info)
        assert len(chunks) == 6

    # --- Integration with parser ---

    def test_integration_parser_chunker(
        self,
        chunker: ParentChildChunker,
        law_metadata: LawMetadata,
        source_info: SourceInfo,
    ) -> None:
        """Test tích hợp: parse → chunk phải hoạt động end-to-end."""
        text = """Chương I
NHỮNG QUY ĐỊNH CHUNG
Điều 1. Phạm vi điều chỉnh
Bộ luật này quy định các quan hệ dân sự.
Điều 2. Công nhận quyền
1. Quyền dân sự được công nhận.
2. Quyền có thể bị hạn chế.
"""
        parser = VietnamLegalParser()
        articles = parser.parse_to_articles(text)
        chunks = chunker.chunk_articles(articles, law_metadata, source_info)

        # Điều 1 (0 Khoản) → 1 chunk, Điều 2 (2 Khoản) → 2 chunks
        assert len(chunks) == 3


# =============================================================================
# TEST: build_law_metadata helper
# =============================================================================

class TestBuildLawMetadata:
    """Tests cho helper function build_law_metadata."""

    def test_basic(self) -> None:
        """Tạo metadata cơ bản."""
        meta = build_law_metadata("BLDS_2015", "Bộ luật Dân sự 2015", 2015)
        assert meta.law_id == "BLDS_2015"
        assert meta.status == "active"

    def test_with_effective_date_string(self) -> None:
        """Effective date dạng string ISO."""
        meta = build_law_metadata(
            "BLDS_2015", "Bộ luật Dân sự 2015", 2015,
            effective_date="2017-01-01",
        )
        assert meta.effective_date is not None
        assert meta.effective_date.year == 2017

    def test_with_domain_tags(self) -> None:
        """Domain tags phải đúng."""
        meta = build_law_metadata(
            "LDD_VBHN", "Luật Đất đai", 2025,
            domain_tags=["đất đai", "bất động sản"],
        )
        assert "đất đai" in meta.domain_tags
