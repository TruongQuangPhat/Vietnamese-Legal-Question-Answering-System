"""Corpus registry loader and validator.

This module provides functionality to:
- Load legal corpus registry from YAML files
- Validate registry entries
- Filter entries by various criteria
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.core.config import get_settings
from src.core.exceptions import RegistryError
from src.ingestion.models import CrawlTarget, LegalStatus, SourceType


class CorpusRegistryLoader:
    """Loads and validates the legal corpus registry.

    This class is responsible for:
    - Loading YAML registry files
    - Validating entries against the schema
    - Filtering by legal status, source type, and other criteria

    Attributes:
        registry_path: Path to the corpus_registry.yml file.
    """

    def __init__(self, registry_path: str | Path):
        """Initialize the registry loader.

        Args:
            registry_path: Path to the corpus_registry.yml file.
        """
        self.registry_path = Path(registry_path)
        self._settings = get_settings()

    def load_registry(self) -> list[CrawlTarget]:
        """Load and validate the corpus registry.

        Loads the YAML file, validates each entry, and returns
        a list of validated CrawlTarget objects.

        Returns:
            List of validated CrawlTarget objects.

        Raises:
            RegistryError: If the file does not exist, is invalid YAML,
                or contains invalid entries.
        """
        if not self.registry_path.exists():
            raise RegistryError(
                f"Registry file not found: {self.registry_path}"
            )

        try:
            with open(self.registry_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise RegistryError(
                f"Invalid YAML in registry file: {e}"
            ) from e

        if not isinstance(data, dict) or "corpus" not in data:
            raise RegistryError(
                "Registry must contain 'corpus' key with list of entries"
            )

        corpus_data = data["corpus"]
        if not isinstance(corpus_data, list):
            raise RegistryError("'corpus' must be a list of entries")

        targets: list[CrawlTarget] = []
        for idx, entry in enumerate(corpus_data):
            if not isinstance(entry, dict):
                raise RegistryError(
                    f"Entry at index {idx} must be a dictionary"
                )

            # Validate required fields
            self._validate_required_fields(entry, idx)

            # Validate URL for pending entries
            if (
                entry.get("crawl_status") == "pending"
                and entry.get("url") is None
            ):
                raise RegistryError(
                    f"Pending entry '{entry.get('law_id', idx)}' must have a URL",
                    law_id=entry.get("law_id"),
                )

            try:
                target = CrawlTarget.model_validate(entry)
                targets.append(target)
            except ValueError as e:
                law_id = entry.get("law_id", f"index_{idx}")
                raise RegistryError(
                    f"Invalid entry '{law_id}': {e}",
                    law_id=law_id,
                ) from e

        return targets

    def _validate_required_fields(self, entry: dict, idx: int) -> None:
        """Validate that required fields are present.

        Args:
            entry: Registry entry dictionary.
            idx: Index of the entry for error messages.

        Raises:
            RegistryError: If required fields are missing.
        """
        required_fields = ["law_id", "name", "tier", "source_domain", "source_type"]

        for field in required_fields:
            if field not in entry:
                raise RegistryError(
                    f"Entry at index {idx} missing required field: {field}"
                )

    def filter_by_legal_status(
        self,
        targets: list[CrawlTarget],
        legal_statuses: list[LegalStatus] | None = None,
    ) -> list[CrawlTarget]:
        """Filter targets by legal status.

        Args:
            targets: List of CrawlTarget objects.
            legal_statuses: List of legal statuses to filter by.
                If None, returns all targets.

        Returns:
            Filtered list of CrawlTarget objects.
        """
        if legal_statuses is None:
            return targets

        return [
            target for target in targets
            if target.status in legal_statuses
        ]

    def filter_by_source_type(
        self,
        targets: list[CrawlTarget],
        source_types: list[SourceType] | None = None,
    ) -> list[CrawlTarget]:
        """Filter targets by source type.

        Args:
            targets: List of CrawlTarget objects.
            source_types: List of source types to filter by.
                If None, returns all targets.

        Returns:
            Filtered list of CrawlTarget objects.
        """
        if source_types is None:
            return targets

        return [
            target for target in targets
            if target.source_type in source_types
        ]

    def validate_trusted_domain(self, url: str) -> bool:
        """Validate that a URL is from a trusted domain.

        Args:
            url: URL to validate.

        Returns:
            True if the URL is from a trusted domain.

        Raises:
            RegistryError: If the URL is not from a trusted domain.
        """
        from urllib.parse import urlparse

        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            raise RegistryError(f"Invalid URL hostname: {url}")

        if self._settings.trusted_domain not in hostname:
            raise RegistryError(
                f"URL '{url}' is not from trusted domain '{self._settings.trusted_domain}'"
            )

        return True
