"""Unit tests for cleaning & normalization module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

import pytest

from src.ingestion.cleaning import (
    extract_legal_text_from_html,
    remove_safe_boilerplate,
    normalize_unicode,
    normalize_whitespace,
    detect_legal_markers,
    LegalMarkersSummary,
    clean_raw_artifact,
    clean_raw_corpus,
    write_cleaning_report,
    trim_to_legal_body,
)

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
