"""Unit tests for raw artifact storage.

Tests cover:
- Saving HTML with metadata
- Content hash computation
- Backup on force refresh
- Metadata JSON contract
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.ingestion.models import MetadataSchema
from src.ingestion.storage import RawArtifactStore


class TestRawArtifactStore:
    """Tests for RawArtifactStore class."""

    @pytest.fixture
    def store(self, tmp_path: Path) -> RawArtifactStore:
        """Create a storage instance with temporary output directory."""
        return RawArtifactStore(tmp_path, crawler_version="v1.0.0-test")

    def test_ensure_output_dir_exists(self, tmp_path: Path) -> None:
        """Test that output directory is created."""
        test_dir = tmp_path / "test_output"
        store = RawArtifactStore(test_dir)

        # RawArtifactStore creates the dir in __init__, so this just verifies it exists
        assert test_dir.exists()

    def test_content_hash_computation(self, store: RawArtifactStore) -> None:
        """Test SHA-256 hash computation."""
        content = b"Hello, World!"
        hash_result = store.content_hash(content)

        # SHA-256 produces 64 hex characters
        assert len(hash_result) == 64
        assert isinstance(hash_result, str)

        # Same content should produce same hash
        assert store.content_hash(content) == hash_result

        # Different content should produce different hash
        assert store.content_hash(b"Different content") != hash_result

    def test_save_html_with_metadata(self, store: RawArtifactStore) -> None:
        """Test saving HTML content and metadata."""
        html_content = b"""<!DOCTYPE html>
<html><head><title>Test</title></head><body><p>Test content</p></body></html>
"""

        metadata = store.save_html(
            law_id="TEST_LAW",
            content=html_content,
            http_status=200,
            name="Test Law",
            tier=1,
            group="Test Group",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
        )

        # Verify metadata
        assert metadata.law_id == "TEST_LAW"
        assert metadata.name == "Test Law"
        assert metadata.crawl_status == "success"
        assert metadata.http_status == 200
        assert metadata.content_hash is not None
        assert len(metadata.content_hash) == 64
        assert metadata.crawler_version == "v1.0.0-test"
        assert metadata.parser_hint == "tvpl_html"

        # Verify files exist
        latest_dir = store.get_latest_dir("TEST_LAW")
        assert latest_dir.exists()

        html_path = latest_dir / "main.html"
        assert html_path.exists()
        assert html_path.read_bytes() == html_content

        metadata_path = latest_dir / "metadata.json"
        assert metadata_path.exists()

    def test_metadata_json_contract(self, store: RawArtifactStore) -> None:
        """Test that metadata.json contains all required fields."""
        store.save_html(
            law_id="METADATA_TEST",
            content=b"<!DOCTYPE html><html></html>",
            http_status=200,
            name="Metadata Test Law",
            tier=2,
            group="Test",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
            effective_date="2025-01-01",
        )

        metadata_path = store.get_latest_dir("METADATA_TEST") / "metadata.json"
        with open(metadata_path) as f:
            data = json.load(f)

        # Required fields
        required_fields = [
            "law_id",
            "name",
            "tier",
            "source_domain",
            "source_type",
            "url",
            "crawl_status",
            "crawled_at",
            "content_hash",
            "crawler_version",
            "parser_hint",
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

        # Verify field values
        assert data["law_id"] == "METADATA_TEST"
        assert data["crawl_status"] == "success"
        assert data["content_hash"] is not None

    def test_save_attachment(self, store: RawArtifactStore) -> None:
        """Test saving attachment files."""
        pdf_content = b"%PDF-1.4 test pdf content"

        attachment_path = store.save_attachment(
            law_id="PDF_LAW",
            content=pdf_content,
            filename="document.pdf",
        )

        assert attachment_path.exists()
        assert attachment_path.read_bytes() == pdf_content
        assert attachment_path.name == "document.pdf"

        # Verify attachments directory structure
        attachments_dir = store.get_latest_dir("PDF_LAW") / "attachments"
        assert attachments_dir.exists()

    def test_backup_existing_on_force(self, store: RawArtifactStore) -> None:
        """Test backup creation on force refresh."""
        # Create initial crawl
        store.save_html(
            law_id="REFRESH_TEST",
            content=b"initial content",
            name="Refresh Test",
            tier=1,
            group="Test",
            source_type="html",
            url="https://test.com",
        )

        # Verify initial content
        latest_dir = store.get_latest_dir("REFRESH_TEST")
        initial_html = (latest_dir / "main.html").read_bytes()
        assert initial_html == b"initial content"

        # Simulate force refresh by creating a new backup
        backup_dir = store._create_backup("REFRESH_TEST")
        assert backup_dir.exists()

        # Old content should be in backup
        backup_html = backup_dir / "main.html"
        assert backup_html.exists()
        assert backup_html.read_bytes() == b"initial content"

        # latest/ should be removed
        assert not latest_dir.exists()

    def test_metadata_exists(self, store: RawArtifactStore) -> None:
        """Test checking if metadata exists."""
        assert not store.metadata_exists("NONEXISTENT")

        store.save_html(
            law_id="EXISTING",
            content=b"test",
            name="Test",
            tier=1,
            group="Test",
            source_type="html",
            url="https://test.com",
        )

        assert store.metadata_exists("EXISTING")

    def test_load_metadata(self, store: RawArtifactStore) -> None:
        """Test loading existing metadata."""
        # No metadata yet
        assert store.load_metadata("NONEXISTENT") is None

        # Create metadata
        expected_metadata = store.save_html(
            law_id="LOAD_TEST",
            content=b"test",
            http_status=200,
            name="Load Test Law",
            tier=1,
            group="Test",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
            effective_date="2025-01-01",
        )

        # Load and verify
        loaded = store.load_metadata("LOAD_TEST")
        assert loaded is not None
        assert loaded.law_id == expected_metadata.law_id
        assert loaded.name == expected_metadata.name
        assert loaded.content_hash == expected_metadata.content_hash

    def test_write_metadata_directly(self, store: RawArtifactStore) -> None:
        """Test writing metadata directly."""
        metadata = MetadataSchema(
            law_id="DIRECT_TEST",
            name="Direct Test Law",
            tier=1,
            group="Test",
            source_domain="thuvienphapluat.vn",
            source_type="html",
            url="https://thuvienphapluat.vn/test.aspx",
            crawl_status="success",
            crawled_at="2026-01-01T00:00:00+00:00",
            content_hash="abc123def456",
            crawler_version="v1.0.0-test",
            parser_hint="tvpl_html",
        )

        metadata_path = store.write_metadata("DIRECT_TEST", metadata)

        assert metadata_path.exists()

        with open(metadata_path) as f:
            data = json.load(f)

        assert data["law_id"] == "DIRECT_TEST"
        assert data["crawl_status"] == "success"

    def test_get_law_dir(self, store: RawArtifactStore) -> None:
        """Test getting law directory path."""
        path = store.get_law_dir("TEST_LAW")

        assert str(path).endswith("TEST_LAW")
        assert path == store.output_dir / "TEST_LAW"

    def test_get_latest_dir(self, store: RawArtifactStore) -> None:
        """Test getting latest directory path."""
        path = store.get_latest_dir("TEST_LAW")

        assert str(path).endswith("TEST_LAW/latest")
        assert path == store.output_dir / "TEST_LAW" / "latest"
