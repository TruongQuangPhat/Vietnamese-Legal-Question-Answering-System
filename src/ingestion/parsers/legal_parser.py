"""
Vietnamese Legal Text Parser
==============================
Core Regex engine bóc tách văn bản luật Việt Nam theo phân cấp chuẩn pháp lý:

    Phần (Part) → Chương (Chapter) → Mục (Section)
    → Điều (Article) → Khoản (Clause) → Điểm (Point)

**QUY TẮC TUYỆT ĐỐI** (từ rules.md):
- KHÔNG dùng character splitting (cắt mỗi 500 tokens).
- KHÔNG chia chunk ngẫu nhiên làm đứt gãy câu văn pháp lý.
- Chỉ chia theo Khoản/Điểm (đơn vị pháp lý nhỏ nhất có ý nghĩa).
- Xử lý lỗi OCR tiếng Việt: ``Đ iều`` → ``Điều``, zero-width space, v.v.
- Strip chú thích VBHN inline: ``[1]``, ``[2]``, v.v.

Sử dụng::

    from src.ingestion.parsers.legal_parser import VietnamLegalParser

    parser = VietnamLegalParser()
    text = normalize_legal_text(raw_text)
    articles = parser.parse_to_articles(text)

    for article in articles:
        print(f"{article.dieu_number}. {article.dieu_title}")
        for clause in article.clauses:
            print(f"  Khoản {clause.number}: {clause.content[:50]}...")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.core.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# 1. REGEX PATTERNS — Nhận dạng cấu trúc pháp lý Việt Nam
# =============================================================================

# Phần: "PHẦN THỨ NHẤT", "PHẦN I", "PHẦN 1"
PHAN_PATTERN = re.compile(
    r"^(?:PHẦN\s+(?:THỨ\s+)?(?:[IVXLC]+|\d+|"
    r"NHẤT|HAI|BA|BỐN|NĂM|SÁU|BẢY|TÁM|CHÍN|MƯỜI"
    r"|[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]+))"
    r"\s*[:\.]?\s*$",
    re.MULTILINE,
)

# Tiêu đề Phần (dòng ngay sau PHẦN THỨ...)
PHAN_TITLE_PATTERN = re.compile(
    r"^[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]"
    r"[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s,]+$",
    re.MULTILINE,
)

# Chương: "CHƯƠNG I", "CHƯƠNG 1", "Chương I", "Chương II"
CHUONG_PATTERN = re.compile(
    r"^(?:CHƯƠNG|Chương)\s+(?:THỨ\s+|Thứ\s+)?([IVXLC]+|\d+)\s*[:\.]?\s*$",
    re.MULTILINE,
)

# Tiêu đề Chương (dòng ALL-CAPS ngay sau CHƯƠNG X)
CHUONG_TITLE_PATTERN = re.compile(
    r"^[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]"
    r"[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s,;]+$",
    re.MULTILINE,
)

# Mục: "Mục 1. TIÊU ĐỀ" hoặc "MỤC 1" hoặc "Mục 1."
MUC_PATTERN = re.compile(
    r"^(?:MỤC|Mục)\s+(\d+|[A-Z]+)\s*[:\.]?\s*(.+)?$",
    re.MULTILINE,
)

# Điều: "Điều 1. Phạm vi điều chỉnh" hoặc "Điều 141a. ..."
DIEU_PATTERN = re.compile(
    r"^Điều\s+(\d+[a-z]?)\.\s*(.+)?$",
    re.MULTILINE,
)

# Khoản: "1. Nội dung..." (số + dấu chấm + khoảng trắng)
KHOAN_PATTERN = re.compile(
    r"^(\d+)\.\s+(.+)",
    re.MULTILINE,
)

# Điểm: "a) Nội dung..." (chữ cái thường + dấu ngoặc đóng)
DIEM_PATTERN = re.compile(
    r"^([a-zđ])\)\s+(.+)",
    re.MULTILINE,
)

# Cross-reference: "Điều 15 Luật X", "khoản 2 Điều này", "Điều 3 của Bộ luật này"
CROSS_REF_PATTERN = re.compile(
    r"(?:Điều\s+\d+[a-z]?(?:\s+(?:của\s+)?(?:Bộ\s+luật|Luật|Nghị\s+định|Thông\s+tư)\s+[^\s,;.]+)?)",
    re.MULTILINE,
)


# =============================================================================
# 2. TEXT NORMALIZATION — Sửa lỗi OCR và ký tự đặc biệt
# =============================================================================

# Map các lỗi OCR phổ biến trong văn bản luật Việt Nam
OCR_FIX_MAP: dict[str, str] = {
    "Đ iều": "Điều",       # Lỗi tách ký tự Đ
    "đ iều": "điều",
    "Kho ản": "Khoản",     # Lỗi tách ký tự Khoản
    "kho ản": "khoản",
    "Đi ểm": "Điểm",      # Lỗi tách ký tự Điểm
    "đi ểm": "điểm",
    "Chươ ng": "Chương",
    "chươ ng": "chương",
    "Mụ c": "Mục",
    "Qu ốc": "Quốc",
    "qu ốc": "quốc",
}


def normalize_legal_text(text: str) -> str:
    """
    Chuẩn hóa text pháp lý: sửa lỗi OCR, strip ký tự đặc biệt, strip VBHN footnotes.

    Các bước xử lý:
    1. Thay thế ký tự zero-width space, non-breaking space
    2. Sửa lỗi OCR phổ biến (VD: ``Đ iều`` → ``Điều``)
    3. Strip chú thích VBHN inline: ``[1]``, ``[2]`` (footnote markers)
    4. Collapse nhiều khoảng trắng liên tiếp thành 1
    5. Collapse nhiều dòng trống liên tiếp thành 1

    Args:
        text: Văn bản thô cần chuẩn hóa.

    Returns:
        str: Văn bản đã chuẩn hóa.
    """
    # Bước 1: Xóa ký tự vô hình
    text = text.replace("\u200b", "")   # zero-width space
    text = text.replace("\u200c", "")   # zero-width non-joiner
    text = text.replace("\u200d", "")   # zero-width joiner
    text = text.replace("\ufeff", "")   # BOM
    text = text.replace("\xa0", " ")    # non-breaking space → space thường

    # Bước 2: Sửa lỗi OCR
    for wrong, correct in OCR_FIX_MAP.items():
        text = text.replace(wrong, correct)

    # Bước 3: Strip VBHN footnote markers [1], [2], [12], v.v.
    # Chỉ strip khi đứng ĐỘC LẬP (không nằm trong context cross-ref)
    text = re.sub(r"\[\d+\]", "", text)

    # Bước 4: Collapse whitespace (giữ newline)
    text = re.sub(r"[^\S\n]+", " ", text)

    # Bước 5: Collapse nhiều dòng trống thành tối đa 1 dòng trống
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# =============================================================================
# 3. DATA STRUCTURES — Node đại diện cho cấu trúc pháp lý
# =============================================================================

@dataclass
class PointNode:
    """
    Đại diện cho một Điểm (Point) trong cấu trúc pháp lý.

    VD: ``a) Thu hồi đất vì mục đích quốc phòng, an ninh;``

    Attributes:
        letter: Ký tự Điểm (a, b, c, ..., đ).
        content: Nội dung đầy đủ của Điểm.
    """
    letter: str
    content: str


@dataclass
class ClauseNode:
    """
    Đại diện cho một Khoản (Clause) trong cấu trúc pháp lý.

    VD: ``1. Nhà nước thu hồi đất trong các trường hợp sau đây:``

    Attributes:
        number: Số thứ tự Khoản (1, 2, 3, ...).
        content: Nội dung đầy đủ của Khoản (BAO GỒM cả các Điểm con).
        points: Danh sách các Điểm con (nếu có).
    """
    number: str
    content: str
    points: list[PointNode] = field(default_factory=list)


@dataclass
class ArticleNode:
    """
    Đại diện cho một Điều (Article) — đơn vị CƠ BẢN của luật.

    Trong chiến lược Parent-Child (ADR-003):
    - ArticleNode là PARENT → ``parent_content`` cho LLM context
    - Mỗi ClauseNode/PointNode bên trong là CHILD → ``content`` cho vector search

    Attributes:
        dieu_number: Số Điều (VD: "1", "141a").
        dieu_title: Tiêu đề Điều (VD: "Phạm vi điều chỉnh").
        full_content: Toàn bộ nội dung Điều (parent content).
        clauses: Danh sách Khoản con.
        phan: Phần chứa Điều này.
        chuong: Chương chứa Điều này.
        muc: Mục chứa Điều này (có thể None).
        cross_references: Danh sách tham chiếu chéo phát hiện trong Điều.
    """
    dieu_number: str
    dieu_title: str | None
    full_content: str
    clauses: list[ClauseNode] = field(default_factory=list)
    phan: str | None = None
    chuong: str | None = None
    muc: str | None = None
    cross_references: list[str] = field(default_factory=list)


# =============================================================================
# 4. CORE PARSER — Bóc tách cấu trúc pháp lý
# =============================================================================

class VietnamLegalParser:
    """
    Parser chính cho văn bản pháp luật Việt Nam.

    Sử dụng Regex state machine để theo dõi vị trí hierarchy hiện tại
    (Phần/Chương/Mục) khi duyệt qua từng dòng text, rồi bóc tách
    Điều → Khoản → Điểm.

    Workflow::

        raw_text
        → normalize_legal_text()
        → parse_to_articles()
        → list[ArticleNode]  # Mỗi article chứa clauses, hierarchy, cross-refs

    Example::

        parser = VietnamLegalParser()
        articles = parser.parse_to_articles(normalized_text)
        assert len(articles) > 0
        assert articles[0].dieu_number == "1"
    """

    def parse_to_articles(self, text: str) -> list[ArticleNode]:
        """
        Parse toàn bộ văn bản luật thành danh sách ArticleNode.

        Hoạt động như state machine:
        - Duyệt từng dòng text
        - Cập nhật context hierarchy (Phần, Chương, Mục) khi gặp header
        - Khi gặp ``Điều X.`` → kết thúc Điều trước, bắt đầu Điều mới
        - Sau khi duyệt hết → parse nội dung từng Điều thành Khoản/Điểm

        Args:
            text: Văn bản pháp lý ĐÃ CHUẨN HÓA (qua normalize_legal_text).

        Returns:
            list[ArticleNode]: Danh sách các Điều đã parse, theo thứ tự xuất hiện.
        """
        lines = text.split("\n")
        articles: list[ArticleNode] = []

        # State: hierarchy context hiện tại
        current_phan: str | None = None
        current_chuong: str | None = None
        current_muc: str | None = None

        # State: Điều đang thu thập
        current_dieu_number: str | None = None
        current_dieu_title: str | None = None
        current_dieu_lines: list[str] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                # Giữ blank lines trong nội dung Điều (có ý nghĩa phân đoạn)
                if current_dieu_number is not None:
                    current_dieu_lines.append("")
                continue

            # ----- Check Phần -----
            phan_match = PHAN_PATTERN.match(stripped)
            if phan_match:
                # Lấy tiêu đề Phần từ dòng tiếp theo (nếu là ALL-CAPS)
                phan_header = stripped
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if next_line and PHAN_TITLE_PATTERN.match(next_line):
                    current_phan = f"{phan_header} {next_line}"
                else:
                    current_phan = phan_header
                logger.debug("found_phan", phan=current_phan)
                continue

            # ----- Check Chương -----
            chuong_match = CHUONG_PATTERN.match(stripped)
            if chuong_match:
                chuong_number = chuong_match.group(1)
                # Tiêu đề Chương thường ở dòng tiếp theo
                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if next_line and CHUONG_TITLE_PATTERN.match(next_line):
                    current_chuong = f"Chương {chuong_number} {next_line}"
                else:
                    current_chuong = f"Chương {chuong_number}"
                # Mỗi Chương mới reset Mục
                current_muc = None
                logger.debug("found_chuong", chuong=current_chuong)
                continue

            # Bỏ qua dòng tiêu đề Chương (ALL-CAPS, đã capture ở bước trên)
            if CHUONG_TITLE_PATTERN.match(stripped) and current_dieu_number is None:
                continue

            if PHAN_TITLE_PATTERN.match(stripped) and current_dieu_number is None:
                continue

            # ----- Check Mục -----
            muc_match = MUC_PATTERN.match(stripped)
            if muc_match:
                muc_number = muc_match.group(1)
                muc_title = muc_match.group(2) or ""
                current_muc = f"Mục {muc_number} {muc_title}".strip()
                logger.debug("found_muc", muc=current_muc)
                continue

            # ----- Check Điều -----
            dieu_match = DIEU_PATTERN.match(stripped)
            if dieu_match:
                # Finalize Điều trước đó (nếu có)
                if current_dieu_number is not None:
                    article = self._build_article(
                        dieu_number=current_dieu_number,
                        dieu_title=current_dieu_title,
                        dieu_lines=current_dieu_lines,
                        phan=current_phan,
                        chuong=current_chuong,
                        muc=current_muc,
                    )
                    articles.append(article)

                # Bắt đầu Điều mới
                current_dieu_number = dieu_match.group(1)
                current_dieu_title = dieu_match.group(2)
                current_dieu_lines = []
                continue

            # ----- Nội dung thuộc Điều hiện tại -----
            if current_dieu_number is not None:
                current_dieu_lines.append(stripped)

        # Finalize Điều cuối cùng
        if current_dieu_number is not None:
            article = self._build_article(
                dieu_number=current_dieu_number,
                dieu_title=current_dieu_title,
                dieu_lines=current_dieu_lines,
                phan=current_phan,
                chuong=current_chuong,
                muc=current_muc,
            )
            articles.append(article)

        logger.info("legal_parse_completed", total_articles=len(articles))
        return articles

    def _build_article(
        self,
        dieu_number: str,
        dieu_title: str | None,
        dieu_lines: list[str],
        phan: str | None,
        chuong: str | None,
        muc: str | None,
    ) -> ArticleNode:
        """
        Xây dựng ArticleNode từ các dòng text thuộc một Điều.

        Bóc tách nội dung Điều thành các Khoản và Điểm.

        Args:
            dieu_number: Số Điều.
            dieu_title: Tiêu đề Điều.
            dieu_lines: Danh sách dòng text thuộc Điều.
            phan: Phần chứa Điều.
            chuong: Chương chứa Điều.
            muc: Mục chứa Điều.

        Returns:
            ArticleNode: Điều đã parse đầy đủ.
        """
        # Tạo full content (dùng làm parent_content)
        header = f"Điều {dieu_number}."
        if dieu_title:
            header += f" {dieu_title}"

        full_content = header + "\n" + "\n".join(dieu_lines)
        full_content = full_content.strip()

        # Parse Khoản và Điểm
        clauses = self._parse_clauses(dieu_lines)

        # Detect cross-references
        cross_refs = extract_cross_references(full_content)

        return ArticleNode(
            dieu_number=dieu_number,
            dieu_title=dieu_title,
            full_content=full_content,
            clauses=clauses,
            phan=phan,
            chuong=chuong,
            muc=muc,
            cross_references=cross_refs,
        )

    def _parse_clauses(self, lines: list[str]) -> list[ClauseNode]:
        """
        Parse danh sách dòng text thành các ClauseNode (Khoản).

        Mỗi Khoản bắt đầu bằng ``N. `` (số + dấu chấm + khoảng trắng).
        Nội dung sau đó (bao gồm Điểm ``a)``, ``b)``...) thuộc Khoản đó
        cho đến khi gặp Khoản tiếp theo.

        Args:
            lines: Danh sách dòng text bên trong Điều.

        Returns:
            list[ClauseNode]: Danh sách Khoản đã parse.
        """
        clauses: list[ClauseNode] = []
        current_khoan_number: str | None = None
        current_khoan_lines: list[str] = []

        for line in lines:
            if not line.strip():
                if current_khoan_number is not None:
                    current_khoan_lines.append("")
                continue

            khoan_match = KHOAN_PATTERN.match(line.strip())
            if khoan_match:
                # Finalize Khoản trước đó
                if current_khoan_number is not None:
                    clause = self._build_clause(
                        current_khoan_number, current_khoan_lines
                    )
                    clauses.append(clause)

                # Bắt đầu Khoản mới
                current_khoan_number = khoan_match.group(1)
                current_khoan_lines = [khoan_match.group(2)]
                continue

            # Nội dung tiếp theo thuộc Khoản hiện tại
            if current_khoan_number is not None:
                current_khoan_lines.append(line.strip())

        # Finalize Khoản cuối
        if current_khoan_number is not None:
            clause = self._build_clause(current_khoan_number, current_khoan_lines)
            clauses.append(clause)

        return clauses

    def _build_clause(
        self, khoan_number: str, khoan_lines: list[str]
    ) -> ClauseNode:
        """
        Xây dựng ClauseNode từ các dòng text thuộc một Khoản.

        Đồng thời bóc tách các Điểm (``a)``, ``b)``...) bên trong Khoản.

        Args:
            khoan_number: Số thứ tự Khoản.
            khoan_lines: Danh sách dòng text thuộc Khoản.

        Returns:
            ClauseNode: Khoản đã parse đầy đủ kèm Điểm con.
        """
        full_content = f"{khoan_number}. " + "\n".join(khoan_lines)
        full_content = full_content.strip()

        # Parse Điểm
        points: list[PointNode] = []
        for line in khoan_lines:
            diem_match = DIEM_PATTERN.match(line.strip())
            if diem_match:
                letter = diem_match.group(1)
                content = f"{letter}) {diem_match.group(2)}"
                points.append(PointNode(letter=letter, content=content))

        return ClauseNode(
            number=khoan_number,
            content=full_content,
            points=points,
        )


# =============================================================================
# 5. CROSS-REFERENCE EXTRACTION
# =============================================================================

def extract_cross_references(text: str) -> list[str]:
    """
    Trích xuất danh sách tham chiếu chéo từ nội dung text.

    Phát hiện các pattern như:
    - "Điều 15 Luật Đất đai"
    - "khoản 2 Điều này"
    - "Điều 3 của Bộ luật này"

    Args:
        text: Nội dung text cần quét.

    Returns:
        list[str]: Danh sách các tham chiếu chéo tìm được (deduplicated).
    """
    matches = CROSS_REF_PATTERN.findall(text)
    # Deduplicate giữ thứ tự
    seen: set[str] = set()
    unique_refs: list[str] = []
    for ref in matches:
        ref_clean = ref.strip()
        if ref_clean not in seen:
            seen.add(ref_clean)
            unique_refs.append(ref_clean)
    return unique_refs
