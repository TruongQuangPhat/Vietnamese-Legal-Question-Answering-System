"""Unit tests for raw corpus audit module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.ingestion.audit import (
    ERROR_MARKERS,
    LEGAL_MARKERS,
    AuditError,
    audit_raw_corpus,
    audit_single_artifact,
    load_registry_law_ids,
    scan_raw_artifacts,
    validate_html,
    validate_metadata,
)


@pytest.fixture
def temp_registry(tmp_path: Path) -> Path:
    """Create a sample registry YAML."""
    registry = tmp_path / "registry.yml"
    registry.write_text(
        """
corpus:
  - law_id: "BLDS_2015"
    name: "Bộ luật Dân sự 2015"
    tier: 1
    group: "Bộ luật cốt lõi"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/van-ban/Bo-luat-dan-su-2015-296215.aspx"
    crawl_status: "crawled"
    priority: "critical"
  - law_id: "LDD_2024"
    name: "Luật Đất đai 2024"
    tier: 2
    group: "Đất đai"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/van-ban/Luat-dat-dai-2024-123.aspx"
    crawl_status: "crawled"
    priority: "high"
  - law_id: "LLP_2022"
    name: "Luật Lao động 2022"
    tier: 2
    group: "Lao động"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/van-ban/Luat-lao-dong-2022-456.aspx"
    crawl_status: "crawled"
    priority: "high"
"""
    )
    return registry


@pytest.fixture
def valid_artifact_dir(tmp_path: Path) -> Path:
    """Create a valid artifact directory with main.html and metadata.json."""
    artifact = tmp_path / "BLDS_2015" / "latest"
    artifact.mkdir(parents=True)

    # Create main.html (size > 10KB)
    html_content = (
        "<!DOCTYPE html><html><body>\n" + "Điều 1. Nội dung luật.\n" * 500 + "</body></html>"
    )
    (artifact / "main.html").write_text(html_content, encoding="utf-8")

    # Create metadata.json with all required fields as per MetadataSchema
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
        "parser_hint": "tvpl_html",
    }
    (artifact / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    return artifact  # Return the latest/ directory containing the files


class TestLoadRegistryLawIds:
    """Tests for load_registry_law_ids function."""

    def test_load_valid_registry(self, temp_registry: Path) -> None:
        """Test loading a valid registry."""
        law_ids = load_registry_law_ids(temp_registry)
        assert law_ids == {"BLDS_2015", "LDD_2024", "LLP_2022"}

    def test_missing_registry(self, tmp_path: Path) -> None:
        """Test missing registry file."""
        with pytest.raises(AuditError, match="not found"):
            load_registry_law_ids(tmp_path / "nonexistent.yml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Test invalid YAML format."""
        bad_yaml = tmp_path / "bad.yml"
        bad_yaml.write_text("corpus:\n  - law_id: BLDS_2015\n    name: Test\n  invalid: :\n")
        with pytest.raises(AuditError, match="YAML parse error"):
            load_registry_law_ids(bad_yaml)

    def test_missing_corpus_key(self, tmp_path: Path) -> None:
        """Test registry missing 'corpus' key."""
        bad_registry = tmp_path / "bad.yml"
        bad_registry.write_text("other: value\n")
        with pytest.raises(AuditError, match="missing 'corpus' key"):
            load_registry_law_ids(bad_registry)

    def test_duplicate_law_ids(self, tmp_path: Path) -> None:
        """Test duplicate law_id detection."""
        dup_registry = tmp_path / "dup.yml"
        dup_registry.write_text(
            """
corpus:
  - law_id: "BLDS_2015"
    name: "Test 1"
  - law_id: "BLDS_2015"
    name: "Test 2"
"""
        )
        with pytest.raises(AuditError, match="Duplicate law_id"):
            load_registry_law_ids(dup_registry)


class TestScanRawArtifacts:
    """Tests for scan_raw_artifacts function."""

    def test_scan_preferred_layout(self, tmp_path: Path) -> None:
        """Scanning finds artifacts with preferred layout (law_id/latest/)."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        law_dir = raw_dir / "BLDS_2015"
        law_dir.mkdir()
        latest = law_dir / "latest"
        latest.mkdir()
        (latest / "main.html").write_text("test")
        (latest / "metadata.json").write_text("{}")

        artifacts = scan_raw_artifacts(raw_dir)
        assert "BLDS_2015" in artifacts
        assert artifacts["BLDS_2015"] == latest

    def test_scan_fallback_layout(self, tmp_path: Path) -> None:
        """Scanning finds artifacts with fallback flat layout."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        law_dir = raw_dir / "LDD_2024"
        law_dir.mkdir()
        (law_dir / "main.html").write_text("test")
        (law_dir / "metadata.json").write_text("{}")

        artifacts = scan_raw_artifacts(raw_dir)
        assert "LDD_2024" in artifacts
        assert artifacts["LDD_2024"] == law_dir

    def test_scan_skips_incomplete(self, tmp_path: Path) -> None:
        """Scanning skips directories missing either file."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()

        law_dir = raw_dir / "INCOMPLETE"
        law_dir.mkdir()
        (law_dir / "main.html").write_text("test")
        # No metadata.json

        artifacts = scan_raw_artifacts(raw_dir)
        assert "INCOMPLETE" not in artifacts

    def test_scan_empty_dir(self, tmp_path: Path) -> None:
        """Scanning returns empty dict if no artifacts."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        artifacts = scan_raw_artifacts(raw_dir)
        assert artifacts == {}

    def test_scan_missing_dir(self, tmp_path: Path) -> None:
        """Scanning returns empty dict if raw_dir doesn't exist."""
        raw_dir = tmp_path / "nonexistent"
        artifacts = scan_raw_artifacts(raw_dir)
        assert artifacts == {}


class TestValidateMetadata:
    """Tests for validate_metadata function."""

    def test_valid_metadata(self, valid_artifact_dir: Path) -> None:
        """Valid metadata passes."""
        metadata_path = valid_artifact_dir / "metadata.json"
        is_valid, metadata, issues = validate_metadata(metadata_path)
        assert is_valid
        assert len(issues) == 0
        assert metadata["law_id"] == "BLDS_2015"

    def test_missing_metadata_file(self, tmp_path: Path) -> None:
        """Missing metadata file fails."""
        is_valid, metadata, issues = validate_metadata(tmp_path / "none.json")
        assert not is_valid
        assert "metadata_json_missing" in issues

    def test_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON fails."""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{ invalid json }")
        is_valid, metadata, issues = validate_metadata(bad_json)
        assert not is_valid
        assert any("invalid_metadata_json" in i for i in issues)

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        """Missing required fields detected."""
        incomplete = tmp_path / "incomplete.json"
        incomplete.write_text('{"law_id": "TEST"}')
        is_valid, metadata, issues = validate_metadata(incomplete)
        assert not is_valid
        assert any("missing_field" in i for i in issues)

    def test_law_id_mismatch(self, valid_artifact_dir: Path) -> None:
        """Metadata law_id mismatch detected."""
        metadata_path = valid_artifact_dir / "metadata.json"
        # Modify to wrong law_id
        metadata = json.loads(metadata_path.read_text())
        metadata["law_id"] = "WRONG_ID"
        metadata_path.write_text(json.dumps(metadata))

        is_valid, _, issues = validate_metadata(metadata_path, expected_law_id="BLDS_2015")
        assert not is_valid
        assert any("metadata_law_id_mismatch" in i for i in issues)

    def test_untrusted_domain(self, tmp_path: Path) -> None:
        """Untrusted source domain detected."""
        metadata = {
            "law_id": "TEST",
            "name": "Test",
            "source_domain": "example.com",
            "source_type": "html",
            "url": "https://example.com/test",
            "crawl_status": "success",
            "content_hash": "abc123",
        }
        path = tmp_path / "meta.json"
        path.write_text(json.dumps(metadata))
        is_valid, _, issues = validate_metadata(path)
        assert not is_valid
        assert "metadata_source_domain_untrusted" in issues

    def test_crawl_status_not_success(self, tmp_path: Path) -> None:
        """Non-success crawl_status fails."""
        metadata = {
            "law_id": "TEST",
            "name": "Test",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/test",
            "crawl_status": "failed",
            "content_hash": "abc123",
        }
        path = tmp_path / "meta.json"
        path.write_text(json.dumps(metadata))
        is_valid, _, issues = validate_metadata(path)
        assert not is_valid
        assert any("metadata_crawl_status_not_success" in i for i in issues)

    def test_missing_content_hash(self, tmp_path: Path) -> None:
        """Missing content_hash fails."""
        metadata = {
            "law_id": "TEST",
            "name": "Test",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/test",
            "crawl_status": "success",
        }
        path = tmp_path / "meta.json"
        path.write_text(json.dumps(metadata))
        is_valid, _, issues = validate_metadata(path)
        assert not is_valid
        assert "metadata_missing_content_hash" in issues


class TestValidateHtml:
    """Tests for validate_html function."""

    def test_valid_html(self, tmp_path: Path) -> None:
        """Valid HTML passes."""
        html = tmp_path / "valid.html"
        html.write_text(
            "<!DOCTYPE html><html><body>\n" + "Điều 1. Nội dung.\n" * 500 + "</body></html>",
            encoding="utf-8",
        )
        size, is_valid, issues = validate_html(html, min_html_size=1000)
        assert size > 1000
        assert is_valid
        assert len(issues) == 0

    def test_missing_html(self, tmp_path: Path) -> None:
        """Missing HTML fails."""
        size, is_valid, issues = validate_html(tmp_path / "missing.html")
        assert size == 0
        assert not is_valid
        assert "html_missing" in issues

    def test_empty_html(self, tmp_path: Path) -> None:
        """Empty HTML fails."""
        html = tmp_path / "empty.html"
        html.write_text("")
        size, is_valid, issues = validate_html(html)
        assert size == 0
        assert not is_valid
        assert "html_empty" in issues

    def test_small_html_warning(self, tmp_path: Path) -> None:
        """Small HTML produces warning but not invalid."""
        html = tmp_path / "small.html"
        html.write_text("<html><body>Điều 1. Short.</body></html>", encoding="utf-8")
        size, is_valid, issues = validate_html(html, min_html_size=10000)
        assert size < 10000
        assert is_valid  # size warning doesn't invalidate
        assert any("html_size_suspiciously_small" in i for i in issues)

    def test_null_bytes(self, tmp_path: Path) -> None:
        """HTML with null bytes fails."""
        html = tmp_path / "null.html"
        html.write_bytes(b"<!DOCTYPE html>\x00\x00<html>")
        size, is_valid, issues = validate_html(html)
        assert not is_valid
        assert "html_contains_null_bytes" in issues

    def test_not_utf8(self, tmp_path: Path) -> None:
        """Non-UTF8 encoding fails."""
        html = tmp_path / "bad_utf8.html"
        # Write bytes that are invalid UTF-8 (0xFF 0xFE is typical BOM for UTF-16/LE, not valid UTF-8 alone)
        html.write_bytes(b"\xff\xfe\x00\x00" + b"Some text"[0:10])
        size, is_valid, issues = validate_html(html)
        assert not is_valid
        assert any("html_not_utf8" in i for i in issues)

    def test_error_page_detection(self, tmp_path: Path) -> None:
        """Error page markers detected."""
        html = tmp_path / "error.html"
        html.write_text("<!DOCTYPE html><html><body>404 Not Found</body></html>", encoding="utf-8")
        size, is_valid, issues = validate_html(html)
        assert not is_valid
        assert any("likely_error_page" in i for i in issues)

    def test_captcha_detection(self, tmp_path: Path) -> None:
        """Captcha page detected."""
        html = tmp_path / "captcha.html"
        html.write_text("Please complete the captcha to continue", encoding="utf-8")
        size, is_valid, issues = validate_html(html)
        assert not is_valid
        assert any("likely_error_page" in i for i in issues)

    def test_login_page_detection(self, tmp_path: Path) -> None:
        """Login page detected."""
        html = tmp_path / "login.html"
        html.write_text("Vui lòng đăng nhập để tiếp tục", encoding="utf-8")
        size, is_valid, issues = validate_html(html)
        assert not is_valid
        assert any("likely_error_page" in i for i in issues)

    def test_no_legal_markers_warning(self, tmp_path: Path) -> None:
        """Missing legal markers produces warning."""
        html = tmp_path / "no_legal.html"
        html.write_text(
            "<html><body>Just some random text without legal markers.</body></html>",
            encoding="utf-8",
        )
        size, is_valid, issues = validate_html(html, min_html_size=1000)
        assert is_valid  # warning doesn't invalidate
        assert "no_legal_markers" in issues


class TestAuditSingleArtifact:
    """Tests for audit_single_artifact function."""

    def test_valid_artifact(self, valid_artifact_dir: Path, tmp_path: Path) -> None:
        """Valid artifact passes audit."""
        registry_entries: dict[str, Any] = {
            "BLDS_2015": {"law_id": "BLDS_2015", "name": "Bộ luật Dân sự 2015"}
        }
        status = audit_single_artifact(
            law_id="BLDS_2015",
            artifact_dir=valid_artifact_dir,
            registry_entries=registry_entries,
            min_html_size=1000,
        )
        assert status.status == "valid"
        assert status.main_html_exists
        assert status.metadata_json_exists
        assert status.html_size_bytes > 1000
        assert len(status.issues) == 0
        assert len(status.warnings) == 0

    def test_missing_main_html(self, tmp_path: Path) -> None:
        """Missing main.html fails."""
        artifact_dir = tmp_path / "test" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "metadata.json").write_text("{}")

        registry_entries: dict[str, Any] = {"TEST": {"law_id": "TEST"}}
        status = audit_single_artifact(
            law_id="TEST",
            artifact_dir=artifact_dir,
            registry_entries=registry_entries,
            min_html_size=1000,
        )
        assert status.status == "invalid"
        assert not status.main_html_exists
        assert "missing_main_html" in status.issues

    def test_missing_metadata_json(self, tmp_path: Path) -> None:
        """Missing metadata.json fails."""
        artifact_dir = tmp_path / "test" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("test content")

        registry_entries: dict[str, Any] = {"TEST": {"law_id": "TEST"}}
        status = audit_single_artifact(
            law_id="TEST",
            artifact_dir=artifact_dir,
            registry_entries=registry_entries,
            min_html_size=1000,
        )
        assert status.status == "invalid"
        assert not status.metadata_json_exists
        assert "missing_metadata_json" in status.issues

    def test_invalid_metadata_json(self, tmp_path: Path) -> None:
        """Invalid JSON in metadata fails."""
        artifact_dir = tmp_path / "test" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("test content")
        (artifact_dir / "metadata.json").write_text("{ invalid json }")

        registry_entries: dict[str, Any] = {"TEST": {"law_id": "TEST"}}
        status = audit_single_artifact(
            law_id="TEST",
            artifact_dir=artifact_dir,
            registry_entries=registry_entries,
            min_html_size=1000,
        )
        assert status.status == "invalid"
        assert status.metadata_valid is False
        assert any("invalid_metadata_json" in i for i in status.issues)

    def test_small_html_warning(self, tmp_path: Path) -> None:
        """Small HTML produces warning."""
        artifact_dir = tmp_path / "test" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("<html>Điều 1. Short.</html>")
        metadata = {
            "law_id": "TEST",
            "name": "Test",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/test",
            "crawl_status": "success",
            "content_hash": "abc123",
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata))

        registry_entries: dict[str, Any] = {"TEST": {"law_id": "TEST"}}
        status = audit_single_artifact(
            law_id="TEST",
            artifact_dir=artifact_dir,
            registry_entries=registry_entries,
            min_html_size=10000,
        )
        assert status.status == "warning"
        assert any("html_size_suspiciously_small" in w for w in status.warnings)

    def test_blocked_page_detection(self, tmp_path: Path) -> None:
        """Blocked/error page detected as invalid."""
        artifact_dir = tmp_path / "test" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("404 Not Found - Page not found")
        metadata = {
            "law_id": "TEST",
            "name": "Test",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/test",
            "crawl_status": "success",
            "content_hash": "abc123",
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata))

        registry_entries: dict[str, Any] = {"TEST": {"law_id": "TEST"}}
        status = audit_single_artifact(
            law_id="TEST",
            artifact_dir=artifact_dir,
            registry_entries=registry_entries,
            min_html_size=1000,
        )
        assert status.status == "invalid"
        assert any("likely_error_page" in i for i in status.issues)

    def test_metadata_law_id_mismatch(self, tmp_path: Path) -> None:
        """Metadata law_id mismatch fails."""
        artifact_dir = tmp_path / "test" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text("test content")
        metadata = {
            "law_id": "WRONG_ID",
            "name": "Test",
            "source_domain": "thuvienphapluat.vn",
            "source_type": "html",
            "url": "https://thuvienphapluat.vn/test",
            "crawl_status": "success",
            "content_hash": "abc123",
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata))

        registry_entries: dict[str, Any] = {"TEST": {"law_id": "TEST"}}
        status = audit_single_artifact(
            law_id="TEST",
            artifact_dir=artifact_dir,
            registry_entries=registry_entries,
            min_html_size=1000,
        )
        assert status.status == "invalid"
        assert any("metadata_law_id_mismatch" in i for i in status.issues)


class TestAuditRawCorpus:
    """Tests for audit_raw_corpus function."""

    def test_full_audit(self, tmp_path: Path) -> None:
        """Full audit produces correct report."""
        # Create registry
        registry = tmp_path / "registry.yml"
        registry.write_text(
            """
corpus:
  - law_id: "BLDS_2015"
    name: "Bộ luật Dân sự 2015"
    tier: 1
    group: "Bộ luật cốt lõi"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/van-ban/Bo-luat-dan-su-2015-296215.aspx"
    crawl_status: "crawled"
    priority: "critical"
  - law_id: "MISSING_LAW"
    name: "Missing Law"
    tier: 2
    group: "Test"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/test"
    crawl_status: "crawled"
    priority: "low"
"""
        )

        # Create raw_dir with one valid artifact
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        artifact_dir = raw_dir / "BLDS_2015" / "latest"
        artifact_dir.mkdir(parents=True)
        (artifact_dir / "main.html").write_text(
            "<!DOCTYPE html><html><body>\n" + "Điều 1. Nội dung.\n" * 500 + "</body></html>"
        )
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
            "parser_hint": "tvpl_html",
        }
        (artifact_dir / "metadata.json").write_text(json.dumps(metadata))

        report = audit_raw_corpus(registry_path=registry, raw_dir=raw_dir, min_html_size=1000)

        assert report["summary"]["registry_entries"] == 2
        assert report["summary"]["raw_artifacts_found"] == 1
        assert report["summary"]["missing_artifacts"] == 1
        assert report["summary"]["valid_artifacts"] == 1
        assert "MISSING_LAW" in report["missing_in_raw"]
        assert "BLDS_2015" not in report["missing_in_raw"]
        assert len(report["items"]) == 2

    def test_extra_artifact_detected(self, tmp_path: Path) -> None:
        """Extra artifact in raw not in registry detected."""
        registry = tmp_path / "registry.yml"
        registry.write_text(
            """
corpus:
  - law_id: "BLDS_2015"
    name: "Test"
    tier: 1
    group: "Test"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/test"
    crawl_status: "crawled"
    priority: "critical"
"""
        )

        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        # Create two artifacts: one in registry, one extra
        for law_id in ["BLDS_2015", "EXTRA_LAW"]:
            artifact_dir = raw_dir / law_id / "latest"
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "main.html").write_text("test")
            metadata = {
                "law_id": law_id,
                "name": "Test",
                "source_domain": "thuvienphapluat.vn",
                "source_type": "html",
                "url": f"https://thuvienphapluat.vn/{law_id}",
                "crawl_status": "success",
                "content_hash": "abc123",
                "crawler_version": "v1.0.0",
                "parser_hint": "tvpl_html",
            }
            (artifact_dir / "metadata.json").write_text(json.dumps(metadata))

        report = audit_raw_corpus(registry_path=registry, raw_dir=raw_dir, min_html_size=1000)
        assert report["summary"]["extra_artifacts"] == 1
        assert "EXTRA_LAW" in report["extra_in_raw"]


class TestErrorMarkers:
    """Tests for error marker detection."""

    def test_error_markers_case_insensitive(self) -> None:
        """Error markers detected case-insensitively."""
        markers = [
            "404 Not Found",
            "403 Forbidden",
            "captcha challenge",
            "VUI LÒNG ĐĂNG NHẬP",
            "Không tìm thấy trang",
            "Cloudflare error",
        ]
        for marker in markers:
            content = f"Some text before {marker} after"
            assert any(m in content.lower() for m in ERROR_MARKERS), (
                f"Marker '{marker}' should be detected"
            )


class TestLegalMarkers:
    """Tests for legal text marker detection."""

    def test_common_legal_markers(self) -> None:
        """Common Vietnamese legal markers are present."""
        expected = {"điều", "khoản", "điểm", "luật", "bộ luật"}
        assert expected.issubset(LEGAL_MARKERS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
