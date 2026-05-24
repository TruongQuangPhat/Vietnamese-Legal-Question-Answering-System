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

class TestExtractLegalText:
    """Tests for HTML text extraction."""

    def test_remove_script_style_noscript(self) -> None:
        html = """
        <html><head><script>var x=1;</script><style>p{color:red;}</style></head>
        <body><noscript>Enable JS</noscript><p>Hello world</p></body></html>
        """
        text = extract_legal_text_from_html(html)
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
        text = extract_legal_text_from_html(html)
        assert "iframe" not in text.lower()
        assert "Submit" not in text
        assert "Important legal content" in text

    def test_preserve_paragraphs(self, simple_html_page: str) -> None:
        text = extract_legal_text_from_html(simple_html_page)
        assert "Điều 1" in text
        assert "Điều 2" in text

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
        lines = cleaned.splitlines()
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

class TestUnicodeNormalization:
    """Tests for Unicode normalization."""

    def test_unicode_normalization_to_nfc(self) -> None:
        # 'ê' can be composed or decomposed; NFC unifies to composed.
        decomposed = "ế"  # e + ̂ + ́ (combining marks)
        expected = "ế"  # precomposed
        normalized, warnings = normalize_unicode(decomposed)
        assert normalized == expected
        assert len(warnings) == 0

    def test_remove_zero_width_characters(self) -> None:
        # Insert zero-width space between letters
        text = "test​world‌and‍more"
        normalized, warnings = normalize_unicode(text)
        assert "testworldandmore" == normalized
        assert len(warnings) == 0

    def test_normalize_non_breaking_spaces(self) -> None:
        text = "Điều 1.\tNội dung."
        normalized, warnings = normalize_unicode(text)
        assert "Điều 1.\tNội dung." == normalized
        assert len(warnings) == 0

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

    def test_preserve_double_newlines_as_paragraph(self) -> None:
        text = "Para1.\n\nPara2.\n\n\n\nPara3."
        normalized = normalize_whitespace(text)
        # Should have at most 2 consecutive blank lines collapsed to 1.
        assert "Para3" in normalized

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
        assert artifact.text_stats.normalized_text_chars > 0
        assert (output_dir / "BLDS_2015" / "normalized.json").exists()

    def test_generate_cleaning_report(self, tmp_path: Path, valid_artifact_dir: Path) -> None:
        raw_dir = tmp_path / "raw"
        (raw_dir / "BLDS_2015" / "latest").mkdir(parents=True)
        # Copy files from valid_artifact_dir
        (raw_dir / "BLDS_2015" / "latest" / "main.html").write_text(
            (valid_artifact_dir / "main.html").read_text()
        )
        (raw_dir / "BLDS_2015" / "latest" / "metadata.json").write_text(
            (valid_artifact_dir / "metadata.json").read_text()
        )

        output_dir = tmp_path / "interim"
        report_path = tmp_path / "report.json"

        report = clean_raw_corpus(
            raw_dir=raw_dir,
            output_dir=output_dir,
            min_text_length=1,
            write_txt=False
        )
        write_cleaning_report(report, report_path)

        assert report_path.exists()
        with report_path.open("r", encoding="utf-8") as f:
            report_data = json.load(f)
        assert "summary" in report_data
        assert report_data["summary"]["total_artifacts"] == 1
        assert len(report_data["items"]) == 1

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
            "crawl_status": "success",
            "content_hash": "abc",
            "crawler_version": "v1",
            "parser_hint": "tvpl_html"
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

    def test_warn_when_article_marker_missing(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        artifact_dir = tmp_path / "art" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("Chương I\nMục 1\nNội dung.")
        meta = {
            "law_id": "NOART",
            "name": "No Article Law",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/noart",
            "crawl_status": "success",
            "content_hash": "abc",
            "crawler_version": "v1",
            "parser_hint": "tvpl_html"
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(meta))

        artifact, _ = clean_raw_artifact(
            (artifact_dir / "main.html", artifact_dir / "metadata.json"),
            output_dir,
            min_text_length=1,
            write_txt=False
        )
        assert artifact is not None
        assert "missing_article_marker" in artifact.warnings

    def test_warn_when_replacement_character_found(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        artifact_dir = tmp_path / "art" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("Điều 1. t�i.")
        meta = {
            "law_id": "BADENC",
            "name": "Bad Encoding",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/bad",
            "crawl_status": "success",
            "content_hash": "abc",
            "crawler_version": "v1",
            "parser_hint": "tvpl_html"
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(meta))

        artifact, _ = clean_raw_artifact(
            (artifact_dir / "main.html", artifact_dir / "metadata.json"),
            output_dir,
            min_text_length=1,
            write_txt=False
        )
        assert artifact is not None
        assert "encoding_replacement_character_found" in artifact.warnings

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
        assert errors  # should have an error about missing file

    def test_handle_invalid_or_unreadable_html_gracefully(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "out"
        artifact_dir = tmp_path / "art" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_bytes(b"\xff\xfe\x00\x00invalid")
        meta = {
            "law_id": "BADHTML",
            "name": "Bad",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://example.com",
            "crawl_status": "success",
            "content_hash": "abc",
            "crawler_version": "v1",
            "parser_hint": "tvpl_html"
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(meta))

        artifact, errors = clean_raw_artifact(
            (artifact_dir / "main.html", artifact_dir / "metadata.json"),
            output_dir,
            min_text_length=1,
            write_txt=False
        )
        # The file might fail to decode; we either get artifact with partial or error.
        # This test just ensures it doesn't crash.
        assert errors or artifact is None

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
