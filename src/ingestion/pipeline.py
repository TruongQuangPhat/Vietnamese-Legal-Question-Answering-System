"""
Ingestion Pipeline Orchestrator
==================================
Kết nối toàn bộ pipeline: Crawl → Parse → Chunk → Save JSONL → Embed → Qdrant.

Đây là ENTRY POINT chính cho quá trình ingestion dữ liệu pháp luật.
Hỗ trợ chạy qua CLI với một lệnh duy nhất.

**Workflow**::

    1. Crawl HTML từ thuvienphapluat.vn  →  data/raw/{law_id}/
    2. Parse HTML → clean text
    3. Parse legal structure → list[ArticleNode]
    4. Chunk → list[LegalChunkNode]
    5. Save → data/processed/{law_id}.jsonl
    6. (Optional) Embed + Upsert → Qdrant

**CLI Usage**::

    # Chạy full pipeline (crawl + parse + chunk + save JSONL)
    python -m src.ingestion.pipeline \\
        --url "https://thuvienphapluat.vn/..." \\
        --law-id BLDS_2015 \\
        --law-name "Bộ luật Dân sự 2015" \\
        --year 2015
    Ex: python -m src.ingestion.pipeline --url "https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx" --law-id BLDS_2015 --law-name "Bộ luật Dân sự 2015" --year 2015
    # Parse từ file HTML đã download sẵn
    python -m src.ingestion.pipeline \\
        --file data/raw/BLDS_2015/main.html \\
        --law-id BLDS_2015 \\
        --law-name "Bộ luật Dân sự 2015" \\
        --year 2015

    # Embed + Ingest vào Qdrant (yêu cầu Qdrant đang chạy)
    python -m src.ingestion.pipeline \\
        --file data/raw/BLDS_2015/main.html \\
        --law-id BLDS_2015 \\
        --law-name "Bộ luật Dân sự 2015" \\
        --year 2015 \\
        --embed --ingest
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import PROJECT_ROOT
from src.core.exceptions import PipelineError
from src.core.logger import configure_logging, get_logger
from src.ingestion.chunkers import ParentChildChunker, build_law_metadata
from src.ingestion.crawler import ThuvienphapluatCrawler
from src.ingestion.parsers.html_parser import ThuvienphapluatHTMLParser
from src.ingestion.parsers.legal_parser import VietnamLegalParser, normalize_legal_text
from src.ingestion.schemas import LegalChunkNode, SourceInfo

logger = get_logger(__name__)


class IngestionPipeline:
    """
    Orchestrator kết nối toàn bộ data pipeline.

    Workflow tuần tự::

        crawl → html_parse → normalize → legal_parse → chunk → save_jsonl
                                                               ↓ (optional)
                                                           embed → qdrant

    Mỗi bước có thể chạy độc lập hoặc kết hợp.
    Kết quả trung gian (JSONL) luôn được lưu để có thể replay.

    Attributes:
        crawler: ThuvienphapluatCrawler instance.
        html_parser: ThuvienphapluatHTMLParser instance.
        legal_parser: VietnamLegalParser instance.
        chunker: ParentChildChunker instance.
    """

    def __init__(self) -> None:
        """Khởi tạo pipeline với các component mặc định."""
        self.crawler = ThuvienphapluatCrawler()
        self.html_parser = ThuvienphapluatHTMLParser()
        self.legal_parser = VietnamLegalParser()
        self.chunker = ParentChildChunker()

    async def run(
        self,
        url: str,
        law_id: str,
        law_name: str,
        year: int,
        effective_date: str | None = None,
        domain_tags: list[str] | None = None,
        output_dir: Path | None = None,
        do_embed: bool = False,
        do_ingest: bool = False,
    ) -> list[LegalChunkNode]:
        """
        Chạy full pipeline: Crawl → Parse → Chunk → Save → (Embed → Qdrant).

        Args:
            url: URL trang luật trên thuvienphapluat.vn.
            law_id: Mã ID chuẩn (VD: "BLDS_2015").
            law_name: Tên đầy đủ của luật.
            year: Năm ban hành.
            effective_date: Ngày hiệu lực "YYYY-MM-DD" (optional).
            domain_tags: Nhãn lĩnh vực (optional).
            output_dir: Thư mục output. Mặc định ``data/processed/``.
            do_embed: Có tạo embedding không (cần BGE-M3 model).
            do_ingest: Có ingest vào Qdrant không (cần Qdrant running).

        Returns:
            list[LegalChunkNode]: Danh sách chunks đã tạo.

        Raises:
            PipelineError: Khi bất kỳ bước nào thất bại.
        """
        logger.info(
            "pipeline_started",
            law_id=law_id,
            url=url,
            do_embed=do_embed,
            do_ingest=do_ingest,
        )

        try:
            # Bước 1: Crawl HTML
            logger.info("step_1_crawl", law_id=law_id)
            html = await self.crawler.fetch_law_page(url)
            await self.crawler.save_raw_html(html, law_id)

            # Bước 2-5: Parse, Chunk, Save
            source_info = SourceInfo(
                url=url,  # type: ignore[arg-type]
                crawled_at=datetime.now(timezone.utc),
            )

            chunks = self._process_html(
                html=html,
                law_id=law_id,
                law_name=law_name,
                year=year,
                effective_date=effective_date,
                domain_tags=domain_tags,
                source_info=source_info,
                output_dir=output_dir,
            )

            # Bước 6-7: Embed + Ingest (optional)
            if do_embed or do_ingest:
                await self._embed_and_ingest(chunks, do_ingest)

            logger.info(
                "pipeline_completed",
                law_id=law_id,
                total_chunks=len(chunks),
            )
            return chunks

        except Exception as e:
            logger.error("pipeline_failed", law_id=law_id, error=str(e))
            raise PipelineError(
                f"Pipeline failed for {law_id}: {e}",
                details={"law_id": law_id, "url": url},
            ) from e

    async def run_from_file(
        self,
        file_path: str | Path,
        law_id: str,
        law_name: str,
        year: int,
        source_url: str,
        effective_date: str | None = None,
        domain_tags: list[str] | None = None,
        output_dir: Path | None = None,
        do_embed: bool = False,
        do_ingest: bool = False,
    ) -> list[LegalChunkNode]:
        """
        Chạy pipeline từ file HTML đã download sẵn (skip bước crawl).

        Phù hợp khi:
        - HTML đã được download thủ công
        - Cần re-parse mà không muốn crawl lại
        - Test với dữ liệu mẫu

        Args:
            file_path: Đường dẫn file HTML.
            law_id: Mã ID chuẩn.
            law_name: Tên đầy đủ.
            year: Năm ban hành.
            source_url: URL gốc (dùng cho metadata).
            effective_date: Ngày hiệu lực (optional).
            domain_tags: Nhãn lĩnh vực (optional).
            output_dir: Thư mục output.
            do_embed: Có tạo embedding không.
            do_ingest: Có ingest vào Qdrant không.

        Returns:
            list[LegalChunkNode]: Danh sách chunks đã tạo.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise PipelineError(
                f"HTML file not found: {file_path}",
                details={"path": str(file_path)},
            )

        logger.info(
            "pipeline_from_file_started",
            law_id=law_id,
            file=str(file_path),
        )

        html = file_path.read_text(encoding="utf-8")

        source_info = SourceInfo(
            url=source_url,  # type: ignore[arg-type]
            crawled_at=datetime.now(timezone.utc),
        )

        chunks = self._process_html(
            html=html,
            law_id=law_id,
            law_name=law_name,
            year=year,
            effective_date=effective_date,
            domain_tags=domain_tags,
            source_info=source_info,
            output_dir=output_dir,
        )

        if do_embed or do_ingest:
            await self._embed_and_ingest(chunks, do_ingest)

        logger.info(
            "pipeline_from_file_completed",
            law_id=law_id,
            total_chunks=len(chunks),
        )
        return chunks

    def _process_html(
        self,
        html: str,
        law_id: str,
        law_name: str,
        year: int,
        effective_date: str | None,
        domain_tags: list[str] | None,
        source_info: SourceInfo,
        output_dir: Path | None,
    ) -> list[LegalChunkNode]:
        """
        Core processing: HTML → clean text → articles → chunks → JSONL.

        Args:
            html: HTML hoặc markdown content.
            law_id: Mã ID luật.
            law_name: Tên luật.
            year: Năm ban hành.
            effective_date: Ngày hiệu lực.
            domain_tags: Nhãn lĩnh vực.
            source_info: Thông tin nguồn.
            output_dir: Thư mục output.

        Returns:
            list[LegalChunkNode]: Danh sách chunks.
        """
        # Bước 2: Parse HTML → clean text
        logger.info("step_2_parse_html", law_id=law_id)
        clean_text = self.html_parser.parse(html)

        # Bước 3: Normalize text
        logger.info("step_3_normalize", law_id=law_id)
        normalized = normalize_legal_text(clean_text)

        # Bước 4: Parse legal structure → ArticleNodes
        logger.info("step_4_legal_parse", law_id=law_id)
        articles = self.legal_parser.parse_to_articles(normalized)
        logger.info(
            "articles_parsed",
            law_id=law_id,
            total_articles=len(articles),
        )

        if not articles:
            raise PipelineError(
                f"No articles found for {law_id}. HTML may have unexpected structure.",
                details={"law_id": law_id, "text_length": len(normalized)},
            )

        # Bước 5: Chunk → LegalChunkNodes
        logger.info("step_5_chunk", law_id=law_id)
        law_metadata = build_law_metadata(
            law_id=law_id,
            law_name=law_name,
            year=year,
            effective_date=effective_date,
            domain_tags=domain_tags,
        )

        chunks = self.chunker.chunk_articles(articles, law_metadata, source_info)

        # Bước 5b: Save JSONL
        if output_dir is None:
            output_dir = PROJECT_ROOT / "data" / "processed"

        self._save_jsonl(chunks, law_id, output_dir)

        return chunks

    def _save_jsonl(
        self,
        chunks: list[LegalChunkNode],
        law_id: str,
        output_dir: Path,
    ) -> Path:
        """
        Lưu chunks ra file JSONL.

        Mỗi dòng trong file là một JSON object đại diện cho 1 chunk,
        tuân thủ schema ``LegalChunkNode``.

        Args:
            chunks: Danh sách chunks cần lưu.
            law_id: Mã ID luật (dùng làm tên file).
            output_dir: Thư mục output.

        Returns:
            Path: Đường dẫn file JSONL đã lưu.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"{law_id}.jsonl"

        with file_path.open("w", encoding="utf-8") as f:
            for chunk in chunks:
                # Pydantic V2 model_dump → JSON serializable dict
                data = chunk.model_dump(mode="json")
                json_line = json.dumps(data, ensure_ascii=False)
                f.write(json_line + "\n")

        logger.info(
            "jsonl_saved",
            law_id=law_id,
            path=str(file_path),
            total_chunks=len(chunks),
            size_bytes=file_path.stat().st_size,
        )
        return file_path

    async def _embed_and_ingest(
        self,
        chunks: list[LegalChunkNode],
        do_ingest: bool,
    ) -> None:
        """
        Embed chunks bằng BGE-M3 và (optional) ingest vào Qdrant.

        Args:
            chunks: Danh sách chunks cần embed.
            do_ingest: Có upsert vào Qdrant không.
        """
        from src.ingestion.embedder import BGEEmbedder
        from src.retrieval.vector_store import QdrantVectorStore

        # Embed
        logger.info("step_6_embed", num_chunks=len(chunks))
        embedder = BGEEmbedder()
        texts = [chunk.content for chunk in chunks]
        vectors = embedder.embed(texts)

        logger.info(
            "embedding_done",
            num_vectors=len(vectors["dense"]),
        )

        # Ingest vào Qdrant
        if do_ingest:
            logger.info("step_7_ingest", num_chunks=len(chunks))
            store = QdrantVectorStore()
            await store.setup_collection()
            count = await store.upsert_chunks(
                chunks=chunks,
                dense_vectors=vectors["dense"],
                sparse_vectors=vectors["sparse"],
            )
            logger.info("ingest_done", points_upserted=count)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main() -> None:
    """
    CLI entry point cho ingestion pipeline.

    Usage::

        python -m src.ingestion.pipeline --help
        python -m src.ingestion.pipeline \\
            --url "https://thuvienphapluat.vn/..." \\
            --law-id BLDS_2015 --law-name "Bộ luật Dân sự 2015" --year 2015

        python -m src.ingestion.pipeline \\
            --file data/raw/BLDS_2015/main.html \\
            --law-id BLDS_2015 --law-name "Bộ luật Dân sự 2015" --year 2015
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="VnLaw-QA Ingestion Pipeline — Thu thập và xử lý văn bản pháp luật VN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ví dụ:
  # Crawl + Parse + Chunk (output: data/processed/BLDS_2015.jsonl)
  python -m src.ingestion.pipeline \\
      --url "https://thuvienphapluat.vn/van-ban/Quyen-dan-su/Bo-luat-dan-su-2015-296215.aspx" \\
      --law-id BLDS_2015 \\
      --law-name "Bộ luật Dân sự 2015" \\
      --year 2015

  # Parse từ file local
  python -m src.ingestion.pipeline \\
      --file data/raw/BLDS_2015/main.html \\
      --law-id BLDS_2015 \\
      --law-name "Bộ luật Dân sự 2015" \\
      --year 2015 \\
      --source-url "https://thuvienphapluat.vn/..."
        """,
    )

    # Input source (URL hoặc file)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--url", type=str, help="URL trang luật trên thuvienphapluat.vn"
    )
    input_group.add_argument(
        "--file", type=str, help="Đường dẫn file HTML đã download"
    )

    # Metadata bắt buộc
    parser.add_argument(
        "--law-id", type=str, required=True,
        help="Mã ID luật (VD: BLDS_2015, LDD_VBHN)"
    )
    parser.add_argument(
        "--law-name", type=str, required=True,
        help="Tên đầy đủ luật"
    )
    parser.add_argument(
        "--year", type=int, required=True,
        help="Năm ban hành"
    )

    # Metadata tùy chọn
    parser.add_argument(
        "--effective-date", type=str, default=None,
        help="Ngày hiệu lực (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--domain-tags", type=str, nargs="+", default=None,
        help="Nhãn lĩnh vực (VD: 'dân sự' 'hợp đồng')"
    )
    parser.add_argument(
        "--source-url", type=str, default=None,
        help="URL gốc (khi dùng --file)"
    )

    # Output
    parser.add_argument(
        "--output", type=str, default=None,
        help="Thư mục output. Mặc định: data/processed/"
    )

    # Optional steps
    parser.add_argument(
        "--embed", action="store_true",
        help="Tạo BGE-M3 embeddings (cần GPU hoặc nhiều RAM)"
    )
    parser.add_argument(
        "--ingest", action="store_true",
        help="Ingest vào Qdrant (cần Qdrant đang chạy)"
    )

    # Logging
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Mức log (mặc định: INFO)"
    )

    args = parser.parse_args()

    # Setup logging
    configure_logging(args.log_level)

    # Setup output dir
    output_dir = Path(args.output) if args.output else None

    # Run pipeline
    pipeline = IngestionPipeline()

    if args.url:
        # Mode: Crawl from URL
        asyncio.run(
            pipeline.run(
                url=args.url,
                law_id=args.law_id,
                law_name=args.law_name,
                year=args.year,
                effective_date=args.effective_date,
                domain_tags=args.domain_tags,
                output_dir=output_dir,
                do_embed=args.embed,
                do_ingest=args.ingest,
            )
        )
    else:
        # Mode: Parse from file
        source_url = args.source_url or f"file://{args.file}"
        asyncio.run(
            pipeline.run_from_file(
                file_path=args.file,
                law_id=args.law_id,
                law_name=args.law_name,
                year=args.year,
                source_url=source_url,
                effective_date=args.effective_date,
                domain_tags=args.domain_tags,
                output_dir=output_dir,
                do_embed=args.embed,
                do_ingest=args.ingest,
            )
        )


if __name__ == "__main__":
    main()
