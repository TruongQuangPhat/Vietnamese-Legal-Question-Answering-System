"""
VnLaw-QA Data Schemas
======================
Pydantic V2 models nghiêm ngặt cho toàn bộ dữ liệu trong pipeline.

**QUY TẮC BẮT BUỘC** (từ rules.md):
- Mọi document chunk PHẢI tuân thủ ``LegalChunkNode`` schema.
- Không dùng ``dict`` raw — luôn validate qua Pydantic.
- Hierarchy phải đúng phân cấp: Phần > Chương > Mục > Điều > Khoản > Điểm.

Sử dụng::

    from src.ingestion.schemas import LegalChunkNode, LawMetadata, Hierarchy

    chunk = LegalChunkNode(
        chunk_id=uuid4(),
        law_metadata=LawMetadata(law_id="BLDS_2015", ...),
        hierarchy=Hierarchy(dieu="Điều 1", ...),
        content="Nội dung khoản...",
        parent_content="Toàn bộ nội dung Điều cha...",
        cross_references=[],
        source_info=SourceInfo(url="https://...", crawled_at=datetime.now()),
    )
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl


class LawMetadata(BaseModel):
    """
    Thông tin metadata về một văn bản luật.

    Attributes:
        law_id: Mã định danh chuẩn (VD: "BLDS_2015", "LDD_VBHN").
        law_name: Tên đầy đủ của luật.
        year: Năm ban hành hoặc năm hợp nhất.
        effective_date: Ngày bắt đầu có hiệu lực.
        expiry_date: Ngày hết hiệu lực (None nếu còn hiệu lực).
        status: Trạng thái hiện tại của văn bản.
        domain_tags: Danh sách nhãn lĩnh vực liên quan.
    """

    law_id: str = Field(..., description="Mã ID chuẩn: VD 'BLDS_2015', 'LDD_VBHN'")
    law_name: str = Field(..., description="Tên đầy đủ của luật")
    year: int = Field(..., description="Năm ban hành hoặc hợp nhất")
    effective_date: date | None = Field(None, description="Ngày có hiệu lực")
    expiry_date: date | None = Field(None, description="Ngày hết hiệu lực")
    status: Literal["active", "inactive", "draft"] = Field(
        "active", description="Trạng thái hiệu lực"
    )
    domain_tags: list[str] = Field(default_factory=list, description="Nhãn lĩnh vực")


class Hierarchy(BaseModel):
    """
    Phân cấp vị trí chunk trong cấu trúc văn bản pháp luật Việt Nam.

    Cấu trúc chuẩn (từ trên xuống)::

        Phần (Part)
          └── Chương (Chapter)
                └── Mục (Section) [tùy có]
                      └── Điều (Article)        ← Parent
                            └── Khoản (Clause) ← Child chunk
                                  └── Điểm (Point)

    Attributes:
        phan: Phần (VD: "Phần thứ nhất").
        chuong: Chương (VD: "Chương I").
        muc: Mục (VD: "Mục 1"), có thể None.
        dieu: Điều — BẮT BUỘC (VD: "Điều 17").
        dieu_title: Tiêu đề của Điều (VD: "Thu hồi đất").
        khoan: Khoản (VD: "Khoản 1"), có thể None.
        diem: Điểm (VD: "Điểm a"), có thể None.
    """

    phan: str | None = Field(None, description="Phần (Part)")
    chuong: str | None = Field(None, description="Chương (Chapter)")
    muc: str | None = Field(None, description="Mục (Section)")
    dieu: str = Field(..., description="Điều (Article) — bắt buộc")
    dieu_title: str | None = Field(None, description="Tiêu đề của Điều")
    khoan: str | None = Field(None, description="Khoản (Clause)")
    diem: str | None = Field(None, description="Điểm (Point)")


class SourceInfo(BaseModel):
    """
    Thông tin nguồn gốc dữ liệu.

    Attributes:
        url: URL gốc trên thuvienphapluat.vn.
        crawled_at: Thời điểm crawl (UTC ISO 8601).
    """

    url: HttpUrl = Field(..., description="URL nguồn gốc")
    crawled_at: datetime = Field(..., description="Thời điểm crawl (UTC)")


class LegalChunkNode(BaseModel):
    """
    Đơn vị dữ liệu cốt lõi — một chunk pháp lý đã được parse và chuẩn hóa.

    Đây là SCHEMA BẮT BUỘC cho mọi dữ liệu đưa vào Qdrant / Neo4j.
    Mọi chunk PHẢI validate qua schema này trước khi ingest.

    **Chiến lược Parent-Child** (ADR-003):
    - ``content``: Nội dung nhỏ (Khoản/Điểm) → dùng để tạo embedding vector,
      giúp tìm kiếm chính xác hơn.
    - ``parent_content``: Toàn bộ Điều cha → cung cấp context đầy đủ cho LLM,
      tránh hallucination do thiếu ngữ cảnh.

    Attributes:
        chunk_id: UUID4 duy nhất cho mỗi chunk.
        law_metadata: Metadata về văn bản luật chứa chunk.
        hierarchy: Vị trí phân cấp trong cấu trúc luật.
        content: Nội dung chunk con (Khoản/Điểm) — dùng cho vector search.
        parent_content: Toàn bộ nội dung Điều cha — dùng làm LLM context.
        cross_references: Danh sách ID tham chiếu chéo (phục vụ GraphRAG).
        source_info: Thông tin nguồn crawl.
    """

    chunk_id: UUID = Field(..., description="UUID4 duy nhất")
    law_metadata: LawMetadata = Field(..., description="Metadata văn bản luật")
    hierarchy: Hierarchy = Field(..., description="Vị trí phân cấp")
    content: str = Field(..., description="Nội dung chunk con (tìm kiếm vector)")
    parent_content: str = Field(..., description="Nội dung Điều cha (context LLM)")
    cross_references: list[str] = Field(
        default_factory=list, description="Danh sách tham chiếu chéo"
    )
    source_info: SourceInfo = Field(..., description="Thông tin nguồn")
