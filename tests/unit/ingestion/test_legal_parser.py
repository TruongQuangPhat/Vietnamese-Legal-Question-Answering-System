"""
Unit Tests — Vietnamese Legal Parser
=======================================
Test suite cho VietnamLegalParser và normalize_legal_text.

Bao gồm tests cho:
1. Normalize text: OCR fix, zero-width space, VBHN footnotes
2. Parse Điều/Khoản/Điểm từ nhiều loại luật khác nhau
3. Hierarchy tracking (Phần/Chương/Mục context)
4. Cross-reference extraction
5. Edge cases: Điều không có Khoản, text rỗng, v.v.
"""

from __future__ import annotations

from src.ingestion.parsers.legal_parser import (
    VietnamLegalParser,
    extract_cross_references,
    normalize_legal_text,
)

# =============================================================================
# FIXTURES — Dữ liệu mẫu (sample data)
# =============================================================================

# Mẫu text giống Bộ luật Dân sự 2015 (BLDS)
SAMPLE_BLDS_TEXT = """
PHẦN THỨ NHẤT
QUY ĐỊNH CHUNG
Chương I
NHỮNG QUY ĐỊNH CHUNG
Điều 1. Phạm vi điều chỉnh
Bộ luật này quy định địa vị pháp lý, chuẩn mực pháp lý về cách ứng xử của cá nhân, pháp nhân.
Điều 2. Công nhận, tôn trọng, bảo vệ và bảo đảm quyền dân sự
1. Ở nước Cộng hòa xã hội chủ nghĩa Việt Nam, các quyền dân sự được công nhận.
2. Quyền dân sự chỉ có thể bị hạn chế theo quy định của luật.
Điều 3. Các nguyên tắc cơ bản của pháp luật dân sự
1. Mọi cá nhân, pháp nhân đều bình đẳng.
2. Cá nhân, pháp nhân xác lập, thực hiện quyền, nghĩa vụ dân sự.
3. Cá nhân, pháp nhân phải xác lập, thực hiện nghĩa vụ thiện chí.
4. Việc xác lập quyền không được xâm phạm đến lợi ích quốc gia.
5. Cá nhân phải tự chịu trách nhiệm về nghĩa vụ dân sự.
""".strip()

# Mẫu text giống Bộ luật Hình sự (BLHS) — có Điều với Khoản + Điểm
SAMPLE_BLHS_TEXT = """
Chương XV
CÁC TỘI XÂM PHẠM TÍNH MẠNG, SỨC KHỎE
Điều 141. Tội hiếp dâm
1. Người nào dùng vũ lực, đe dọa dùng vũ lực hoặc lợi dụng tình trạng không thể tự vệ được của nạn nhân thì bị phạt tù từ 02 năm đến 07 năm.
2. Phạm tội thuộc một trong các trường hợp sau đây, thì bị phạt tù từ 07 năm đến 15 năm:
a) Có tổ chức;
b) Đối với người mà người phạm tội có trách nhiệm chăm sóc;
c) Nhiều người hiếp một người;
đ) Gây thương tích từ 31% đến 60%;
3. Phạm tội thuộc trường hợp đặc biệt nghiêm trọng thì bị phạt tù từ 12 năm đến 20 năm.
""".strip()

# Mẫu text giống Luật Đất đai (LDD) — có Mục
SAMPLE_LDD_TEXT = """
Chương II
QUYỀN VÀ TRÁCH NHIỆM CỦA NHÀ NƯỚC
Mục 1. QUYỀN CỦA NHÀ NƯỚC ĐỐI VỚI ĐẤT ĐAI
Điều 13. Quyền của Nhà nước đối với đất đai
1. Nhà nước đại diện chủ sở hữu về đất đai theo quy định của Hiến pháp.
2. Nhà nước thực hiện quyền định đoạt đối với đất đai.
Điều 17. Nhà nước thu hồi đất, trưng dụng đất
1. Nhà nước thu hồi đất trong các trường hợp sau đây:
a) Thu hồi đất vì mục đích quốc phòng, an ninh;
b) Thu hồi đất để phát triển kinh tế - xã hội vì lợi ích quốc gia;
c) Thu hồi đất do vi phạm pháp luật về đất đai;
2. Nhà nước trưng dụng đất trong trường hợp thật cần thiết theo quy định tại Điều 82 của Luật này.
""".strip()


# =============================================================================
# TEST: normalize_legal_text
# =============================================================================

class TestNormalizeLegalText:
    """Tests cho hàm chuẩn hóa text pháp lý."""

    def test_fix_ocr_dieu(self) -> None:
        """Sửa lỗi OCR phổ biến: 'Đ iều' → 'Điều'."""
        text = "Đ iều 1. Phạm vi điều chỉnh"
        result = normalize_legal_text(text)
        assert "Điều 1. Phạm vi điều chỉnh" in result

    def test_fix_ocr_khoan(self) -> None:
        """Sửa lỗi OCR: 'Kho ản' → 'Khoản'."""
        text = "Kho ản 2 Đ iều này quy định"
        result = normalize_legal_text(text)
        assert "Khoản" in result
        assert "Điều" in result

    def test_strip_zero_width_space(self) -> None:
        """Xóa zero-width space (U+200B)."""
        text = "Điều\u200b 1.\u200b Phạm vi"
        result = normalize_legal_text(text)
        assert "\u200b" not in result
        assert "Điều 1. Phạm vi" in result

    def test_strip_non_breaking_space(self) -> None:
        """Thay non-breaking space (U+00A0) bằng space thường."""
        text = "Điều\xa01.\xa0Phạm vi"
        result = normalize_legal_text(text)
        assert "\xa0" not in result
        assert "Điều 1. Phạm vi" in result

    def test_strip_vbhn_footnotes(self) -> None:
        """Strip chú thích VBHN inline [1], [2], [12]."""
        text = "Nội dung khoản này[1] được sửa đổi[12] theo Luật mới[2]."
        result = normalize_legal_text(text)
        assert "[1]" not in result
        assert "[12]" not in result
        assert "[2]" not in result
        assert "Nội dung khoản này được sửa đổi theo Luật mới." in result

    def test_collapse_whitespace(self) -> None:
        """Gom nhiều khoảng trắng liên tiếp thành 1."""
        text = "Điều   1.    Phạm   vi"
        result = normalize_legal_text(text)
        assert "Điều 1. Phạm vi" in result

    def test_collapse_empty_lines(self) -> None:
        """Gom nhiều dòng trống liên tiếp thành tối đa 1 dòng trống."""
        text = "Điều 1.\n\n\n\n\nĐiều 2."
        result = normalize_legal_text(text)
        assert "\n\n\n" not in result

    def test_strip_bom(self) -> None:
        """Xóa BOM (U+FEFF) ở đầu file."""
        text = "\ufeffĐiều 1. Phạm vi"
        result = normalize_legal_text(text)
        assert result.startswith("Điều")

    def test_empty_text(self) -> None:
        """Text rỗng trả về rỗng."""
        assert normalize_legal_text("") == ""
        assert normalize_legal_text("   ") == ""


# =============================================================================
# TEST: VietnamLegalParser.parse_to_articles
# =============================================================================

class TestParseToArticles:
    """Tests cho parser chính."""

    def setup_method(self) -> None:
        """Khởi tạo parser trước mỗi test."""
        self.parser = VietnamLegalParser()

    # --- Test cơ bản: BLDS ---

    def test_parse_blds_article_count(self) -> None:
        """Parse BLDS sample phải ra đúng 3 Điều."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert len(articles) == 3

    def test_parse_blds_article_numbers(self) -> None:
        """Số Điều phải đúng thứ tự."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert articles[0].dieu_number == "1"
        assert articles[1].dieu_number == "2"
        assert articles[2].dieu_number == "3"

    def test_parse_blds_article_titles(self) -> None:
        """Tiêu đề Điều phải chính xác."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert articles[0].dieu_title == "Phạm vi điều chỉnh"
        assert "Công nhận" in articles[1].dieu_title

    def test_parse_blds_article_with_no_clauses(self) -> None:
        """Điều 1 không có Khoản → clauses rỗng."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert len(articles[0].clauses) == 0

    def test_parse_blds_article_with_clauses(self) -> None:
        """Điều 2 có 2 Khoản."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert len(articles[1].clauses) == 2

    def test_parse_blds_article_with_5_clauses(self) -> None:
        """Điều 3 có 5 Khoản."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert len(articles[2].clauses) == 5

    # --- Test Khoản + Điểm: BLHS ---

    def test_parse_blhs_article_count(self) -> None:
        """Parse BLHS sample phải ra 1 Điều."""
        articles = self.parser.parse_to_articles(SAMPLE_BLHS_TEXT)
        assert len(articles) == 1

    def test_parse_blhs_clause_count(self) -> None:
        """Điều 141 có 3 Khoản."""
        articles = self.parser.parse_to_articles(SAMPLE_BLHS_TEXT)
        assert len(articles[0].clauses) == 3

    def test_parse_blhs_points(self) -> None:
        """Khoản 2 Điều 141 có các Điểm a, b, c, đ."""
        articles = self.parser.parse_to_articles(SAMPLE_BLHS_TEXT)
        clause_2 = articles[0].clauses[1]
        assert len(clause_2.points) == 4
        assert clause_2.points[0].letter == "a"
        assert clause_2.points[1].letter == "b"
        assert clause_2.points[2].letter == "c"
        assert clause_2.points[3].letter == "đ"

    def test_parse_blhs_point_content(self) -> None:
        """Nội dung Điểm phải bao gồm ký tự + ngoặc."""
        articles = self.parser.parse_to_articles(SAMPLE_BLHS_TEXT)
        point_a = articles[0].clauses[1].points[0]
        assert point_a.content.startswith("a) ")
        assert "Có tổ chức" in point_a.content

    # --- Test Mục: LDD ---

    def test_parse_ldd_with_muc(self) -> None:
        """Parse LDD sample phải tracking được Mục."""
        articles = self.parser.parse_to_articles(SAMPLE_LDD_TEXT)
        assert len(articles) == 2
        # Cả 2 Điều đều thuộc Mục 1
        assert articles[0].muc is not None
        assert "Mục 1" in articles[0].muc

    def test_parse_ldd_chuong(self) -> None:
        """Cả 2 Điều thuộc Chương II."""
        articles = self.parser.parse_to_articles(SAMPLE_LDD_TEXT)
        assert articles[0].chuong is not None
        assert "II" in articles[0].chuong

    def test_parse_ldd_article_with_points(self) -> None:
        """Điều 17 Khoản 1 có 3 Điểm a, b, c."""
        articles = self.parser.parse_to_articles(SAMPLE_LDD_TEXT)
        dieu_17 = articles[1]
        assert dieu_17.dieu_number == "17"
        assert len(dieu_17.clauses) == 2
        assert len(dieu_17.clauses[0].points) == 3

    # --- Test hierarchy ---

    def test_phan_tracking(self) -> None:
        """Parser phải tracking được Phần."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert articles[0].phan is not None
        assert "PHẦN THỨ NHẤT" in articles[0].phan

    def test_chuong_tracking(self) -> None:
        """Parser phải tracking được Chương."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert articles[0].chuong is not None
        assert "Chương I" in articles[0].chuong

    # --- Test full_content ---

    def test_full_content_includes_header(self) -> None:
        """full_content phải bắt đầu với 'Điều N. Title'."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert articles[0].full_content.startswith("Điều 1.")

    def test_full_content_includes_body(self) -> None:
        """full_content phải chứa nội dung."""
        articles = self.parser.parse_to_articles(SAMPLE_BLDS_TEXT)
        assert "địa vị pháp lý" in articles[0].full_content

    # --- Edge cases ---

    def test_empty_text_returns_empty(self) -> None:
        """Text rỗng phải trả về danh sách rỗng."""
        articles = self.parser.parse_to_articles("")
        assert len(articles) == 0

    def test_no_articles_found(self) -> None:
        """Text không chứa Điều phải trả về rỗng."""
        articles = self.parser.parse_to_articles(
            "Đây là text bình thường không có cấu trúc pháp lý."
        )
        assert len(articles) == 0


# =============================================================================
# TEST: extract_cross_references
# =============================================================================

class TestExtractCrossReferences:
    """Tests cho hàm trích xuất tham chiếu chéo."""

    def test_basic_cross_ref(self) -> None:
        """Detect tham chiếu Điều đơn giản."""
        text = "theo quy định tại Điều 15 Luật Đất đai."
        refs = extract_cross_references(text)
        assert len(refs) >= 1
        assert any("Điều 15" in ref for ref in refs)

    def test_cross_ref_bo_luat(self) -> None:
        """Detect tham chiếu Bộ luật."""
        text = "Điều 3 của Bộ luật này"
        refs = extract_cross_references(text)
        assert len(refs) >= 1

    def test_multiple_cross_refs(self) -> None:
        """Detect nhiều tham chiếu trong cùng text."""
        text = "quy định tại Điều 52 và Điều 53 của Bộ luật này"
        refs = extract_cross_references(text)
        assert len(refs) >= 2

    def test_no_cross_refs(self) -> None:
        """Text không có tham chiếu → danh sách rỗng."""
        text = "Đây là nội dung bình thường."
        refs = extract_cross_references(text)
        assert len(refs) == 0

    def test_deduplication(self) -> None:
        """Tham chiếu trùng lặp phải deduplicate."""
        text = "Điều 15 Luật X quy định. Xem thêm Điều 15 Luật X."
        refs = extract_cross_references(text)
        # Phải deduplicate
        unique = set(refs)
        assert len(refs) == len(unique)
