"""Unit tests for the registry loader.

Tests cover:
- Loading valid registry
- Rejecting untrusted domains
- Filtering by status and type
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.core.exceptions import RegistryError
from src.ingestion.models import CrawlStatus, LegalStatus, SourceType
from src.ingestion.registry import CorpusRegistryLoader


class TestCorpusRegistryLoader:
    """Tests for CorpusRegistryLoader class."""

    @pytest.fixture
    def valid_registry_yaml(self) -> str:
        """Return a valid registry YAML string."""
        return """
corpus:
  - law_id: "BLDS_2015"
    name: "Bộ luật Dân sự 2015"
    tier: 1
    group: "Bộ luật cốt lõi"
    domain_tags: ["dân sự", "hợp đồng"]
    status: "active"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/van-ban/DAN-SU/test.aspx"
    crawl_status: "pending"
    priority: "critical"
    notes: "Test law"
"""

    @pytest.fixture
    def valid_registry_file(self, valid_registry_yaml: str) -> Path:
        """Create a temporary registry file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write(valid_registry_yaml)
            path = Path(f.name)
        yield path
        path.unlink()

    def test_load_valid_registry(self, valid_registry_file: Path) -> None:
        """Test loading a valid registry file."""
        loader = CorpusRegistryLoader(valid_registry_file)
        targets = loader.load_registry()

        assert len(targets) == 1
        assert targets[0].law_id == "BLDS_2015"
        assert targets[0].name == "Bộ luật Dân sự 2015"
        assert targets[0].tier == 1
        assert targets[0].source_domain == "thuvienphapluat.vn"
        assert targets[0].source_type == SourceType.HTML
        assert targets[0].crawl_status == CrawlStatus.PENDING
        assert targets[0].priority.value == "critical"

    def test_reject_untrusted_domain(self) -> None:
        """Test that untrusted domains are rejected."""
        registry_yaml = """
corpus:
  - law_id: "TEST"
    name: "Test Law"
    tier: 1
    group: "Test"
    source_domain: "example.com"
    source_type: "html"
    url: "https://example.com/test"
    crawl_status: "pending"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write(registry_yaml)
            path = Path(f.name)

        try:
            loader = CorpusRegistryLoader(path)
            with pytest.raises(RegistryError, match="thuvienphapluat.vn"):
                loader.load_registry()
        finally:
            path.unlink()

    def test_reject_missing_url_when_pending(self) -> None:
        """Test that pending entries without URL are rejected."""
        registry_yaml = """
corpus:
  - law_id: "TEST"
    name: "Test Law"
    tier: 1
    group: "Test"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    crawl_status: "pending"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write(registry_yaml)
            path = Path(f.name)

        try:
            loader = CorpusRegistryLoader(path)
            with pytest.raises(RegistryError, match="must have a URL"):
                loader.load_registry()
        finally:
            path.unlink()

    def test_allow_null_url_for_planned(self) -> None:
        """Test that planned entries can have null URL."""
        registry_yaml = """
corpus:
  - law_id: "TEST"
    name: "Test Law"
    tier: 2
    group: "Test"
    source_domain: "thuvienphapluat.vn"
    source_type: "unknown"
    status: "planned"
    crawl_status: "manual_review"
    url: null
    priority: "low"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write(registry_yaml)
            path = Path(f.name)

        try:
            loader = CorpusRegistryLoader(path)
            targets = loader.load_registry()

            assert len(targets) == 1
            assert targets[0].url is None
            assert targets[0].status == LegalStatus.PLANNED
            assert targets[0].crawl_status == CrawlStatus.MANUAL_REVIEW
        finally:
            path.unlink()

    def test_file_not_found(self) -> None:
        """Test that non-existent file raises error."""
        loader = CorpusRegistryLoader("/nonexistent/path.yml")
        with pytest.raises(RegistryError, match="not found"):
            loader.load_registry()

    def test_invalid_yaml(self) -> None:
        """Test that invalid YAML raises error."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write("invalid: yaml: content: [")
            path = Path(f.name)

        try:
            loader = CorpusRegistryLoader(path)
            with pytest.raises(RegistryError, match="Invalid YAML"):
                loader.load_registry()
        finally:
            path.unlink()

    def test_missing_corpus_key(self) -> None:
        """Test that missing 'corpus' key raises error."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write("laws: []")
            path = Path(f.name)

        try:
            loader = CorpusRegistryLoader(path)
            with pytest.raises(RegistryError, match="'corpus'"):
                loader.load_registry()
        finally:
            path.unlink()

    def test_multiple_entries(self) -> None:
        """Test loading multiple registry entries."""
        registry_yaml = """
corpus:
  - law_id: "LAW1"
    name: "Law 1"
    tier: 1
    group: "Group A"
    source_domain: "thuvienphapluat.vn"
    source_type: "html"
    url: "https://thuvienphapluat.vn/law1.aspx"
    crawl_status: "pending"
    priority: "high"
  - law_id: "LAW2"
    name: "Law 2"
    tier: 2
    group: "Group B"
    source_domain: "thuvienphapluat.vn"
    source_type: "pdf"
    url: "https://thuvienphapluat.vn/law2.pdf"
    crawl_status: "crawled"
    priority: "medium"
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yml", delete=False, encoding="utf-8"
        ) as f:
            f.write(registry_yaml)
            path = Path(f.name)

        try:
            loader = CorpusRegistryLoader(path)
            targets = loader.load_registry()

            assert len(targets) == 2
            assert targets[0].law_id == "LAW1"
            assert targets[1].law_id == "LAW2"
        finally:
            path.unlink()

    def test_filter_by_legal_status(self, valid_registry_file: Path) -> None:
        """Test filtering by legal status."""
        loader = CorpusRegistryLoader(valid_registry_file)
        targets = loader.load_registry()

        # Filter by active status
        filtered = loader.filter_by_legal_status(targets, [LegalStatus.ACTIVE])
        assert len(filtered) == 1

        # Filter by non-matching status
        filtered = loader.filter_by_legal_status(targets, [LegalStatus.INACTIVE])
        assert len(filtered) == 0

    def test_filter_by_source_type(self, valid_registry_file: Path) -> None:
        """Test filtering by source type."""
        loader = CorpusRegistryLoader(valid_registry_file)
        targets = loader.load_registry()

        # Filter by matching type
        filtered = loader.filter_by_source_type(targets, [SourceType.HTML])
        assert len(filtered) == 1

        # Filter by non-matching type
        filtered = loader.filter_by_source_type(targets, [SourceType.PDF])
        assert len(filtered) == 0

    def test_validate_trusted_domain(self, valid_registry_file: Path) -> None:
        """Test domain validation."""
        loader = CorpusRegistryLoader(valid_registry_file)

        # Valid domain
        assert loader.validate_trusted_domain("https://thuvienphapluat.vn/test")

        # Invalid domain
        with pytest.raises(RegistryError, match="not from trusted domain"):
            loader.validate_trusted_domain("https://example.com/test")
