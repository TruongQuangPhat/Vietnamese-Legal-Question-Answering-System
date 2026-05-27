"""Unit tests for cleaning & normalization module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

import pytest

import src.ingestion.cleaning as cleaning
from src.ingestion.cleaning import (
    extract_legal_text_from_html,
    remove_safe_boilerplate,
    normalize_unicode,
    normalize_whitespace,
    detect_legal_markers,
    LegalMarkersSummary,
    trim_to_legal_body,
)
from src.services.cleaning_service import clean_raw_artifact

# --- Fixtures ---

@pytest.fixture
def simple_html_page() -> str:
    return """
<!DOCTYPE html>
<html>
<head>
    <script>var x = 5;</script>
    <style>.legal { font-weight: bold; }</style>
</head>
<body>
    <div>
        THƯ VIỆN PHÁP LUẬT
    </div>
    <div class="content">
        <h1>BỘ LUẬT DÂN SỰ 2015</h1>
        <p>Điều 1. Quy định chung.</p>
        <p>1. Nội dung khoản thứ nhất.</p>
        <p>2. Nội dung khoản thứ hai.</p>
        <p>&nbsp;</p>
        <p>Điều 2. Quy định khác.</p>
        <p>a) Điểm a</p>
        <p>b) Điểm b</p>
    </div>
</body>
</html>
"""

@pytest.fixture
def valid_artifact_dir(tmp_path: Path) -> Path:
    """Create a valid artifact directory with main.html and metadata.json."""
    artifact = tmp_path / "BLDS_2015" / "latest"
    artifact.mkdir(parents=True)

    html = """
    <!DOCTYPE html>
    <html><body>
    Điều 1. Nội dung luật.\n
    Điều 2. Nội dung khác.\n
    1. Khoản một.\n
    a) Điểm a.\n
    </body></html>
    """
    (artifact / "main.html").write_text(html, encoding="utf-8")

    metadata = {
        "law_id": "BLDS_2015",
        "name": "Bộ luật Dân sự 2015",
        "tier": 1,
        "group": "Bộ luật cốt lõi",
        "source_domain": "thuvienphapluat.vn",
        "source_type": "html",
        "url": "https://thuvienphapluat.vn/van-ban/Bo-luat-dan-su-2015-296215.aspx",
        "crawl_status": "success",
        "http_status": 200,
        "crawled_at": "2026-05-22T10:00:00Z",
        "content_hash": "sha256:" + "a" * 64,
        "crawler_version": "v1.0.0",
        "parser_hint": "tvpl_html"
    }
    (artifact / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    return artifact

# --- Tests ---

def _extract_and_normalize_html(html: str) -> str:
    """Run public extraction and normalization helpers for synthetic HTML."""
    extracted, _ = extract_legal_text_from_html(html)
    normalized, _ = normalize_unicode(extracted)
    return normalize_whitespace(normalized)

def _tvpl_content_html(*paragraphs: str) -> str:
    """Wrap paragraphs in the preferred TVPL legal-body selector."""
    filler = " ".join(["Nội dung bổ sung để vượt ngưỡng chọn nội dung."] * 20)
    paragraph_html = "\n".join(paragraphs)
    return f"""
    <html>
      <body>
        <div id="divContentDoc">
          <div class="content1">
            {paragraph_html}
            <p>Điều 3. Nội dung kiểm thử.</p>
            <p>{filler}</p>
          </div>
        </div>
      </body>
    </html>
    """

class TestTrimToLegalBody:
    """Tests for trim_to_legal_body function."""

    def test_trim_start_marker_quoc_hoi(self) -> None:
        text = "Header noise\nQUỐC HỘI\nCỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐiều 1. Nội dung 1\nĐiều 2. Nội dung 2\n" + "Content " * 100
        trimmed = trim_to_legal_body(text)
        assert trimmed.startswith("QUỐC HỘI")
        assert "Header noise" not in trimmed

    def test_trim_start_marker_dieu1(self) -> None:
        text = "More noise\nĐiều 1. Nội dung luật 1\nĐiều 2. Nội dung luật 2\n" + "Content " * 100
        trimmed = trim_to_legal_body(text)
        assert trimmed.startswith("Điều 1")
        assert "More noise" not in trimmed

    def test_trim_end_marker_footer(self) -> None:
        text = "Điều 1. Nội dung\nĐiều 2. Nội dung\nĐiều 3. Nội dung\n" + "Content " * 20 + "\n\nVăn bản liên quan\nLink 1\nLink 2"
        trimmed = trim_to_legal_body(text)
        assert "Điều 3" in trimmed
        assert "Văn bản liên quan" not in trimmed

    def test_no_markers_keep_original(self) -> None:
        text = "Just some random text without markers"
        trimmed = trim_to_legal_body(text)
        assert trimmed == text

class TestP0StartTrimmingRepair:
    """Stage 2A tests for P0 start-trimming failure modes."""

    def test_fragmented_header_keeps_article_1_before_later_amendment(self) -> None:
        text = "\n".join([
            "Trang đầu",
            "L",
            "UẬT AN NINH MẠNG",
            "Điều 1. Phạm vi điều chỉnh.",
            "Điều 2. Giải thích từ ngữ.",
            "Nội dung thân luật chính. " * 12,
            "LUẬT SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU",
            "Điều 50. Điều khoản sửa đổi.",
            "Điều 51. Hiệu lực thi hành.",
            "Nội dung phần sửa đổi. " * 30,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert "Điều 1. Phạm vi điều chỉnh." in trimmed[:250]
        assert not trimmed.startswith("LUẬT SỬA ĐỔI")

    def test_lanm_style_keeps_beginning_when_later_section_has_many_law_markers(self) -> None:
        text = "\n".join([
            "L",
            "UẬT AN NINH MẠNG",
            "Điều 1. Phạm vi điều chỉnh.",
            "Điều 2. Đối tượng áp dụng.",
            "Điều 3. Giải thích từ ngữ.",
            "Nội dung thân luật chính. " * 10,
            "LUẬT SỬA ĐỔI LUẬT ĐẦU TƯ, LUẬT DOANH NGHIỆP, LUẬT AN NINH MẠNG",
            "Điều 64. Sửa đổi, bổ sung một số điều.",
            "Điều 65. Điều khoản chuyển tiếp.",
            "Nội dung phần sửa đổi. " * 30,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert trimmed.startswith("L\nUẬT AN NINH MẠNG")
        assert "Điều 1. Phạm vi điều chỉnh." in trimmed[:200]

    def test_lvl_style_does_not_start_at_article_32(self) -> None:
        text = "\n".join([
            "LUẬT VIỆC LÀM",
            "Điều 1. Phạm vi điều chỉnh.",
            "Điều 2. Đối tượng áp dụng.",
            "Điều 3. Giải thích từ ngữ.",
            "Nội dung thân luật chính. " * 15,
            "Điều 32. Chính sách hỗ trợ việc làm.",
            "Nội dung Điều 32. " * 30,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert trimmed.startswith("LUẬT VIỆC LÀM")
        assert not trimmed.startswith("Điều 32.")
        assert "Điều 1. Phạm vi điều chỉnh." in trimmed[:160]

    def test_vbhn_style_chooses_consolidated_body_before_source_law_notes(self) -> None:
        text = "\n".join([
            "VĂN BẢN HỢP",
            "NHẤT",
            "Điều 1. Phạm vi điều chỉnh.",
            "Điều 2. Đối tượng áp dụng.",
            "Điều 3. Nguyên tắc áp dụng.",
            "Nội dung văn bản hợp nhất. " * 10,
            "LUẬT SỬA ĐỔI, BỔ SUNG MỘT SỐ ĐIỀU CỦA LUẬT GỐC",
            "Điều 70. Điều khoản sửa đổi.",
            "Điều 71. Điều khoản thi hành.",
            "Nội dung ghi chú luật nguồn. " * 30,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert trimmed.startswith("VĂN BẢN HỢP\nNHẤT")
        assert "Điều 1. Phạm vi điều chỉnh." in trimmed[:180]
        assert not trimmed.startswith("LUẬT SỬA ĐỔI")

class TestStage2GSourceLawNoteTrimming:
    """Stage 2G tests for pre-body source-law/amendment notes."""

    def test_lhngd_style_source_law_note_is_trimmed_before_main_body(self) -> None:
        text = "\n".join([
            "Luật số 81/2025/QH15 ngày 24 tháng 6 năm 2025 của Quốc hội sửa đổi, bổ sung một số điều của Luật Tổ chức Tòa án nhân dân, có hiệu lực kể từ ngày 01 tháng 7 năm 2025.",
            "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam; Quốc hội ban hành Luật Hôn nhân và gia đình[1].",
            "Chương I",
            "NHỮNG QUY ĐỊNH CHUNG",
            "Điều 1. Phạm vi điều chỉnh",
            "Luật này quy định chế độ hôn nhân và gia đình.",
            "Điều 2. Những nguyên tắc cơ bản của chế độ hôn nhân và gia đình",
            "Nội dung thân luật chính. " * 20,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert not trimmed.startswith("Luật số 81/2025/QH15")
        assert (
            trimmed.startswith("Căn cứ Hiến pháp")
            or "Quốc hội ban hành Luật Hôn nhân và gia đình" in trimmed[:180]
        )
        assert "Điều 1. Phạm vi điều chỉnh" in trimmed[:260]

    def test_ltatgt_style_source_law_note_is_trimmed_before_main_body(self) -> None:
        text = "\n".join([
            "Luật số 118/2025/QH15 ngày 10 tháng 12 năm 2025 của Quốc hội sửa đổi, bổ sung một số điều của 10 luật có liên quan đến an ninh, trật tự, có hiệu lực kể từ ngày 01 tháng 7 năm 2026.",
            "Căn cứ Hiến pháp nước Cộng hòa xã hội chủ nghĩa Việt Nam; Quốc hội ban hành Luật Trật tự, an toàn giao thông đường bộ[1].",
            "Chương I",
            "NHỮNG QUY ĐỊNH CHUNG",
            "Điều 1. Phạm vi điều chỉnh",
            "Luật này quy định về quy tắc, phương tiện, người tham gia giao thông đường bộ.",
            "Điều 2. Giải thích từ ngữ",
            "Nội dung thân luật chính. " * 20,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert not trimmed.startswith("Luật số 118/2025/QH15")
        assert (
            trimmed.startswith("Căn cứ Hiến pháp")
            or "Quốc hội ban hành Luật Trật tự, an toàn giao thông đường bộ" in trimmed[:220]
        )
        assert "Điều 1. Phạm vi điều chỉnh" in trimmed[:300]

    def test_normal_law_start_is_not_overtrimmed(self) -> None:
        text = "\n".join([
            "Quốc hội ban hành Luật Việc làm.",
            "Chương I",
            "NHỮNG QUY ĐỊNH CHUNG",
            "Điều 1. Phạm vi điều chỉnh.",
            "Luật này quy định chính sách hỗ trợ tạo việc làm.",
            "Điều 2. Giải thích từ ngữ.",
            "Nội dung thân luật chính. " * 20,
        ])

        trimmed = trim_to_legal_body(text, {"selection_strategy": "preferred_tvpl_selector"})

        assert trimmed.startswith("Quốc hội ban hành Luật Việc làm.")
        assert "Điều 1. Phạm vi điều chỉnh." in trimmed[:180]

class TestExtractLegalText:
    """Tests for HTML text extraction."""

    def test_remove_script_style_noscript(self) -> None:
        html = """
        <html><head><script>var x=1;</script><style>p{color:red;}</style></head>
        <body><noscript>Enable JS</noscript><p>Hello world</p></body></html>
        """
        text, _ = extract_legal_text_from_html(html)
        assert "var x=1" not in text
        assert "color:red" not in text
        assert "Enable JS" not in text
        assert "Hello world" in text

    def test_remove_iframe_form_button(self) -> None:
        html = """
        <body>
        <iframe src="nav.html"></iframe>
        <form><input type="text"><button>Submit</button></form>
        <p>Important legal content</p>
        </body>
        """
        text, _ = extract_legal_text_from_html(html)
        assert "iframe" not in text.lower()
        assert "Submit" not in text
        assert "Important legal content" in text

    def test_extract_legal_body_over_header(self) -> None:
        html = """
        <html>
        <body>
            <div id="header"><h1>Page Title</h1><p>Welcome to the site</p></div>
            <div id="main-content">
                <h2>Legal Body</h2>
                <p>Điều 1. Phạm vi điều chỉnh.</p>
                <p>Điều 2. Đối tượng áp dụng.</p>
            </div>
            <div id="footer">Footer content</div>
        </body>
        </html>
        """
        text, _ = extract_legal_text_from_html(html)
        assert "Điều 1" in text
        assert "Điều 2" in text
        assert "Welcome to the site" not in text
        assert "Legal Body" in text

    def test_extract_ignores_navigation_density(self) -> None:
        html = """
        <html>
        <body>
            <div id="nav">
                <a href="/1">Điều 1</a><a href="/2">Điều 2</a><a href="/3">Điều 3</a>
                <a href="/4">Điều 4</a><a href="/5">Điều 5</a>
            </div>
            <div id="content">
                <p>Điều 1. This is the actual content of article 1. It is long and detailed.</p>
                <p>Điều 2. This is the actual content of article 2. It is also long.</p>
            </div>
        </body>
        </html>
        """
        text, _ = extract_legal_text_from_html(html)
        # Content div should win due to length and marker density vs links
        assert "actual content of article 1" in text
        assert "actual content of article 2" in text
        # If it chose the content div, the nav div text is not included
        assert "Điều 3" not in text

class TestP2AHtmlExtractionFragmentation:
    """Stage 2D tests for inline-heavy TVPL extraction patterns."""

    def test_inline_span_font_split_words_do_not_create_newline_fragments(self) -> None:
        html = _tvpl_content_html(
            "<p>Qu<span>ốc</span> hội ban hành Luật.</p>",
            "<p>Điều 1. Phạm vi điều chỉnh.</p>",
            "<p>Cơ quan, t<span>ổ</span><span> chức</span>, cá nhân.</p>",
            "<p>Điều 2. Giải thích từ ngữ.</p>",
        )

        text = _extract_and_normalize_html(html)

        assert "Quốc hội" in text
        assert "tổ chức" in text
        assert "Qu\nốc" not in text
        assert "t\nổ" not in text

    def test_inline_font_formatting_nodes_join_as_inline_text(self) -> None:
        html = _tvpl_content_html(
            "<p>An ninh <font>mạng</font> là nội dung được bảo vệ.</p>",
            "<p>Bảo <b>vệ</b> <i>an ninh</i> <u>mạng</u>.</p>",
            "<p>Tham chiếu <a href='/x'>văn bản</a> liên quan.</p>",
            "<p>Điều 1. Phạm vi điều chỉnh.</p>",
            "<p>Điều 2. Giải thích từ ngữ.</p>",
        )

        text = _extract_and_normalize_html(html)

        assert "An ninh mạng" in text
        assert "Bảo vệ" in text
        assert "m\nạng" not in text
        assert "Bảo\nvệ" not in text

    def test_block_boundaries_remain_between_article_clause_and_point(self) -> None:
        html = _tvpl_content_html(
            "<p>Điều 1. Tên điều.</p>",
            "<p>1. Nội dung khoản.</p>",
            "<p>a) Nội dung điểm.</p>",
            "<p>Điều 2. Điều tiếp theo.</p>",
        )

        lines = _extract_and_normalize_html(html).splitlines()

        assert "Điều 1. Tên điều." in lines
        assert "1. Nội dung khoản." in lines
        assert "a) Nội dung điểm." in lines
        assert lines.index("Điều 1. Tên điều.") < lines.index("1. Nội dung khoản.")
        assert lines.index("1. Nội dung khoản.") < lines.index("a) Nội dung điểm.")

    def test_table_td_legal_body_preserves_blocks_without_inline_splits(self) -> None:
        html = _tvpl_content_html(
            """
            <table>
              <tr>
                <td>
                  <p>Ủy<span> ban</span> thường vụ Quốc hội.</p>
                  <p>Điều 1. Phạm vi điều chỉnh.</p>
                  <p>Điều 2. Giải thích từ ngữ.</p>
                </td>
              </tr>
            </table>
            """,
        )

        text = _extract_and_normalize_html(html)

        assert "Ủy ban thường vụ Quốc hội" in text
        assert "Ủy\nban" not in text
        assert "Điều 1. Phạm vi điều chỉnh." in text

    def test_preferred_selector_still_preserves_detectable_articles(self) -> None:
        html = _tvpl_content_html(
            "<p>Luật này quy định về t<span>ổ</span><span> chức</span>.</p>",
            "<p>Điều 1. Phạm vi điều chỉnh.</p>",
            "<p>Điều 2. Đối tượng áp dụng.</p>",
        )

        text = _extract_and_normalize_html(html)
        markers = detect_legal_markers(text)

        assert markers.contains_article
        assert markers.article_count_estimate >= 2
        assert "Điều 1. Phạm vi điều chỉnh." in text
        assert "Điều 2. Đối tượng áp dụng." in text
        assert "tổ chức" in text

class TestBoilerplateRemoval:
    """Tests for boilerplate removal."""

    def test_remove_common_boilerplate(self) -> None:
        text = "\n".join([
            "THƯ VIỆN PHÁP LUẬT",
            "Đăng nhập",
            "Đăng ký",
            "Điều 1. Nội dung luật.",
            "Tra cứu pháp luật"
        ])
        cleaned = remove_safe_boilerplate(text)
        assert "THƯ VIỆN PHÁP LUẬT" not in cleaned
        assert "Đăng nhập" not in cleaned
        assert "Đăng ký" not in cleaned
        assert "Tra cứu pháp luật" not in cleaned
        assert "Điều 1. Nội dung luật." in cleaned

    def test_preserve_legal_markers(self) -> None:
        text = "\n".join([
            "THƯ VIỆN PHÁP LUẬT",
            "Điều 1. Quy định chung.",
            "Chương II",
            "Mục 3",
            "Văn bản hợp nhất"
        ])
        cleaned = remove_safe_boilerplate(text)
        assert "THƯ VIỆN PHÁP LUẬT" not in cleaned
        assert "Điều 1. Quy định chung." in cleaned
        assert "Chương II" in cleaned
        assert "Mục 3" in cleaned
        assert "Văn bản hợp nhất" in cleaned

    def test_preserve_clause_numbering(self) -> None:
        text = "\n".join([
            "THƯ VIỆN PHÁP LUẬT",
            "1. Khoản thứ nhất.",
            "2. Khoản thứ hai."
        ])
        cleaned = remove_safe_boilerplate(text)
        assert "THƯ VIỆN PHÁP LUẬT" not in cleaned
        assert "1. Khoản thứ nhất." in cleaned
        assert "2. Khoản thứ hai." in cleaned

    def test_preserve_bare_clause_numbering(self) -> None:
        # Bare numbering may represent legal clause/point markers when HTML splits
        # the marker and the content into separate lines.
        text = "\n".join([
            "THƯ VIỆN PHÁP LUẬT",
            "1.",
            "2.",
            "a)"
        ])
        cleaned = remove_safe_boilerplate(text)
        assert "THƯ VIỆN PHÁP LUẬT" not in cleaned
        assert "1." in cleaned
        assert "2." in cleaned
        assert "a)" in cleaned

    def test_preserve_point_labels(self) -> None:
        text = "\n".join([
            "Văn bản liên quan",
            "a) Điểm a.",
            "b) Điểm b.",
            "c) Điểm c."
        ])
        cleaned = remove_safe_boilerplate(text)
        assert "Văn bản liên quan" not in cleaned
        assert "a) Điểm a." in cleaned
        assert "b) Điểm b." in cleaned
        assert "c) Điểm c." in cleaned

class TestUnicodeNormalization:
    """Tests for Unicode normalization."""

    def test_unicode_normalization_to_nfc(self) -> None:
        decomposed = "ế"
        expected = "ế"
        normalized, warnings = normalize_unicode(decomposed)
        assert normalized == expected
        assert len(warnings) == 0

    def test_remove_zero_width_characters(self) -> None:
        text = "test​world‌and‍more"
        normalized, warnings = normalize_unicode(text)
        assert "testworldandmore" == normalized

    def test_normalize_non_breaking_spaces(self) -> None:
        text = "Điều 1.\tNội dung."
        normalized, warnings = normalize_unicode(text)
        assert "Điều 1.\tNội dung." == normalized

    def test_remove_bom(self) -> None:
        text = "﻿Điều 1. Nội dung."
        normalized, warnings = normalize_unicode(text)
        assert not normalized.startswith("﻿")
        assert "Điều 1. Nội dung." in normalized

    def test_warn_on_replacement_character(self) -> None:
        text = "t�i"
        normalized, warnings = normalize_unicode(text)
        assert "encoding_replacement_character_found" in warnings

class TestWhitespaceNormalization:
    """Tests for whitespace normalization."""

    def test_collapse_excessive_whitespace(self) -> None:
        text = "  Line1   with   spaces  \n\n\n\nLine2"
        normalized = normalize_whitespace(text)
        assert "Line1 with spaces" in normalized
        assert "Line2" in normalized

    def test_no_tabs(self) -> None:
        text = "Line1\tTabbed\nLine2"
        normalized = normalize_whitespace(text)
        assert "\t" not in normalized

class TestP1LineFragmentRepair:
    """Stage 2A tests for conservative line-fragment repair."""

    def test_join_split_article_marker_and_number(self) -> None:
        normalized = normalize_whitespace("Điều\n32. Nội dung")
        assert normalized == "Điều 32. Nội dung"

    def test_join_lowercase_dieu_intra_word_split(self) -> None:
        normalized = normalize_whitespace("đ\niều")
        assert normalized == "điều"

    def test_join_lowercase_muc_intra_word_split(self) -> None:
        normalized = normalize_whitespace("m\nục")
        assert normalized == "mục"

    def test_join_viec_intra_word_split(self) -> None:
        normalized = normalize_whitespace("Vi\nệc")
        assert normalized == "Việc"

    def test_preserve_article_to_clause_boundary(self) -> None:
        text = "Điều 1. Tên điều\n1. Nội dung khoản"
        normalized = normalize_whitespace(text)
        assert normalized.splitlines() == [
            "Điều 1. Tên điều",
            "1. Nội dung khoản",
        ]

    def test_preserve_point_label(self) -> None:
        normalized = normalize_whitespace("a) nội dung")
        assert normalized == "a) nội dung"

class TestStage2HEncodedFooterArtifacts:
    """Stage 2H tests for conservative encoded footer artifact cleanup."""

    def test_remove_standalone_base64_artifact_after_signature(self) -> None:
        text = "\n".join([
            "Điều 10. Hiệu lực thi hành",
            "CHỦ TỊCH QUỐC HỘI Nguyễn Sinh Hùng",
            "LdABoAHUAdgBpAGUAbgBwAGgAYQBwAGwAdQBhAHQALgB2AG4A",
        ])

        cleaned = cleaning.remove_encoded_footer_artifacts(text)

        assert "CHỦ TỊCH QUỐC HỘI Nguyễn Sinh Hùng" in cleaned
        assert "LdABoAHUAdgBpAGUAbgBwAGgAYQBwAGwAdQBhAHQALgB2AG4A" not in cleaned

    def test_remove_repeated_encoded_artifact_lines(self) -> None:
        encoded = "LdABoAHUAdgBpAGUAbgBwAGgAYQBwAGwAdQBhAHQALgB2AG4A"
        text = "\n".join([
            "Điều 10. Hiệu lực thi hành",
            "CHỦ TỊCH QUỐC HỘI Nguyễn Sinh Hùng",
            encoded,
            encoded,
            encoded,
        ])

        cleaned = cleaning.remove_encoded_footer_artifacts(text)

        assert "CHỦ TỊCH QUỐC HỘI Nguyễn Sinh Hùng" in cleaned
        assert encoded not in cleaned

    def test_remove_tvpl_encoded_marker_around_tail_signature(self) -> None:
        text = "\n".join([
            "VABWAFAATABfADIAMAAyADYAMAA1ADEAOQA=",
            "CHỦ TỊCH QUỐC HỘI Nguyễn Sinh Hùng",
        ])

        cleaned = cleaning.remove_encoded_footer_artifacts(text)

        assert cleaned == "CHỦ TỊCH QUỐC HỘI Nguyễn Sinh Hùng"

    def test_preserve_normal_legal_lines_with_numbers_and_slashes(self) -> None:
        text = "\n".join([
            "Luật số 85/2015/QH13",
            "Điều 1. Phạm vi điều chỉnh",
            "01/07/2026",
            "Mã HS 0101.21.00",
        ])

        cleaned = cleaning.remove_encoded_footer_artifacts(text)

        assert cleaned.splitlines() == text.splitlines()

    def test_preserve_short_uppercase_legal_table_abbreviations(self) -> None:
        text = "\n".join(["STT", "DMA", "DET", "PMA"])

        cleaned = cleaning.remove_encoded_footer_artifacts(text)

        assert cleaned.splitlines() == ["STT", "DMA", "DET", "PMA"]

class TestLegalMarkersDetection:
    """Tests for legal marker detection."""

    def test_detect_article_marker(self) -> None:
        text = "Điều 1. Quy định chung.\nĐiều 2. Khác."
        markers = detect_legal_markers(text)
        assert markers.contains_article
        assert markers.article_count_estimate == 2

    def test_detect_clause_numbering(self) -> None:
        text = "1. Khoản một.\n2. Khoản hai.\n3. Khoản ba."
        markers = detect_legal_markers(text)
        assert markers.contains_clause_numbering

    def test_detect_point_labeling(self) -> None:
        text = "a) Điểm a.\nb) Điểm b.\nc) Điểm c."
        markers = detect_legal_markers(text)
        assert markers.contains_point_labeling

    def test_detect_chapter_and_part(self) -> None:
        text = "Phần đầu\nChương I\nMục 3"
        markers = detect_legal_markers(text)
        assert markers.contains_part
        assert markers.contains_chapter
        assert markers.contains_section

class TestFullArtifactCleaning:
    """Tests for cleaning a single raw artifact."""

    def test_generate_normalized_json(self, valid_artifact_dir: Path, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        main_html = valid_artifact_dir / "main.html"
        meta_json = valid_artifact_dir / "metadata.json"

        artifact, errors = clean_raw_artifact(
            (main_html, meta_json),
            output_dir,
            min_text_length=1,
            write_txt=False
        )
        assert errors == []
        assert artifact is not None
        assert artifact.law_id == "BLDS_2015"
        assert artifact.normalized_text
        assert (output_dir / "BLDS_2015" / "normalized.json").exists()

    def test_metadata_fallback_logic(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        artifact_dir = tmp_path / "art" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("Điều 1. Nội dung")
        # Use 'name' instead of 'law_name', 'url' instead of 'source_url'
        meta = {
            "law_id": "FALLBACK_TEST",
            "name": "Fallback Law Name",
            "url": "https://example.com/law",
            "source_domain": "example.com",
            "source_type": "html"
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(meta))

        artifact, _ = clean_raw_artifact(
            (artifact_dir / "main.html", artifact_dir / "metadata.json"),
            output_dir,
            min_text_length=1,
            write_txt=False
        )
        assert artifact is not None
        assert artifact.law_name == "Fallback Law Name"
        assert artifact.source_url == "https://example.com/law"

    def test_warn_when_text_is_suspiciously_short(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        artifact_dir = tmp_path / "art" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("Điều 1. Chỉ.")
        meta = {
            "law_id": "SHORT",
            "name": "Short Law",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/short",
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(meta))

        artifact, _ = clean_raw_artifact(
            (artifact_dir / "main.html", artifact_dir / "metadata.json"),
            output_dir,
            min_text_length=1000,
            write_txt=False
        )
        assert artifact is not None
        assert "text_suspiciously_short" in artifact.warnings

    def test_handle_missing_main_html_gracefully(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        artifact_dir = tmp_path / "art" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "metadata.json").write_text("{}")

        artifact, errors = clean_raw_artifact(
            (artifact_dir / "main.html", artifact_dir / "metadata.json"),
            output_dir,
            min_text_length=1,
            write_txt=False
        )
        assert artifact is None
        assert errors

class TestCorpusWideRegression:
    """Regression tests for corpus-wide failure modes seen in v0.4."""

    def test_nav_phap_luat_not_start(self) -> None:
        # Navigation with "Pháp Luật" links should not be the start
        html = """
        <html><body>
            <div id="nav">
                <a href="/1">Pháp Luật Việt Nam</a>
                <a href="/2">Tra cứu Luật</a>
            </div>
            <div id="content">
                <h1>LUẬT ĐẤT ĐAI 2024</h1>
                <p>Điều 1. Phạm vi điều chỉnh.</p>
                <p>Điều 2. Đối tượng áp dụng.</p>
                <p>Điều 3. Nguyên tắc sử dụng đất.</p>
                <p>Đây là nội dung chi tiết của Luật Đất Đai năm 2024 với rất nhiều thông tin chi tiết để đảm bảo vượt qua ngưỡng validation.</p>
                <p>Nội dung bổ sung để đảm bảo đủ 500 ký tự cho _has_sufficient_legal_evidence.</p>
                <p>"a" * 500</p>
            </div>
        </body></html>
        """
        text, _ = extract_legal_text_from_html(html)
        trimmed = trim_to_legal_body(text)
        assert trimmed.startswith("LUẬT ĐẤT ĐAI 2024")
        assert "Pháp Luật Việt Nam" not in trimmed[:100]

    def test_pre_body_tabs_not_trimming_early(self) -> None:
        # Tabs like "Liên quan hiệu lực" might contain markers but shouldn't trigger start
        html = """
        <html><body>
            <div class="tabs">
                <span class="tab">Liên quan hiệu lực: Luật này có hiệu lực từ ngày...</span>
                <span class="tab">Điều 1. Xem chi tiết</span>
            </div>
            <div id="main">
                <h1>LUẬT HÀNH CHÍNH</h1>
                <p>Điều 1. Quy định chung.</p>
                <p>Điều 2. Đối tượng.</p>
                <p>Điều 3. Phạm vi.</p>
                <p>"b" * 600</p>
            </div>
        </body></html>
        """
        text, _ = extract_legal_text_from_html(html)
        trimmed = trim_to_legal_body(text)
        assert trimmed.startswith("LUẬT HÀNH CHÍNH")
        assert "Liên quan hiệu lực" not in trimmed[:100]

    def test_tooltip_article_ignored(self) -> None:
        # Tooltip with "Điều 1" before actual body should be ignored
        html = """
        <html><body>
            <div class="tooltip">Điều 1. Xem nhanh nội dung</div>
            <div id="content">
                <h1>LUẬT TỔ CHỨC CHÍNH PHỦ</h1>
                <p>Điều 1. Phạm vi.</p>
                <p>Điều 2. Đối tượng.</p>
                <p>Điều 3. Nguyên tắc.</p>
                <p>"c" * 600</p>
            </div>
        </body></html>
        """
        text, _ = extract_legal_text_from_html(html)
        trimmed = trim_to_legal_body(text)
        assert trimmed.startswith("LUẬT TỔ CHỨC CHÍNH PHỦ")
        assert "Xem nhanh nội dung" not in trimmed[:100]

    def test_nav_density_loses_to_content(self) -> None:
        # Nav div with many Điều links should lose to content div with actual paragraphs
        html = """
        <html><body>
            <div id="sidebar">
                <a href="/1">Điều 1</a><a href="/2">Điều 2</a><a href="/3">Điều 3</a>
                <a href="/4">Điều 4</a><a href="/5">Điều 5</a><a href="/6">Điều 6</a>
            </div>
            <div id="main">
                <p>Điều 1. Nội dung chi tiết của điều 1. Rất dài và chi tiết để đảm bảo điểm cao.</p>
                <p>Điều 2. Nội dung chi tiết của điều 2. Rất dài và chi tiết để đảm bảo điểm cao.</p>
                <p>Điều 3. Nội dung chi tiết của điều 3. Rất dài và chi tiết để đảm bảo điểm cao.</p>
                <p>"d" * 600</p>
            </div>
        </body></html>
        """
        text, _ = extract_legal_text_from_html(html)
        assert "Nội dung chi tiết" in text
        assert "Điều 6" not in text

    def test_full_noisy_page_trimming(self) -> None:
        # Full noisy page like TVPL
        html = """
        <html><body>
            <div id="header">THƯ VIỆN PHÁP LUẬT - Đăng nhập - Tra cứu</div>
            <div id="nav">Menu chính - Pháp luật - Văn bản mới nhất</div>
            <div id="content">
                <h1>BỘ LUẬT DÂN SỰ 2015</h1>
                <p>Điều 1. Phạm vi điều chỉnh.</p>
                <p>Điều 2. Đối tượng áp dụng.</p>
                <p>Điều 3. Nguyên tắc cơ bản.</p>
                <p>Nội dung rất dài để đảm bảo vượt qua các ngưỡng validation và không bị trim nhầm.</p>
                <p>"e" * 600</p>
                <div id="footer">Văn bản liên quan - Xem thêm - Bản quyền TVPL</div>
            </div>
            <div id="site-footer">Footer site chung</div>
        </body></html>
        """
        text, _ = extract_legal_text_from_html(html)
        trimmed = trim_to_legal_body(text)
        assert trimmed.startswith("BỘ LUẬT DÂN SỰ 2015")
        assert "THƯ VIỆN PHÁP LUẬT" not in trimmed[:100]
        assert "Footer site chung" not in trimmed[-100:]

    def test_no_overtrimming_post_body_marker(self) -> None:
        # End marker appears after substantial body, should trim but not destroy body
        text = "Điều 1. Nội dung 1\nĐiều 2. Nội dung 2\nĐiều 3. Nội dung 3\n" + ("Nội dung " * 20) + "\n\nVăn bản liên quan\nLink 1"
        trimmed = trim_to_legal_body(text)
        assert "Điều 3" in trimmed
        assert "Văn bản liên quan" not in trimmed
        assert "Nội dung " in trimmed

    pytest.main([__file__, "-v"])
