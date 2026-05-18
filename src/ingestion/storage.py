"""Raw artifact storage management.

This module provides functionality to:
- Save raw HTML, PDF, DOC, DOCX files
- Write metadata.json files
- Compute content hashes
- Handle force refresh with backups
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.exceptions import StorageError
from src.ingestion.models import MetadataSchema


class RawArtifactStore:
    """Manages storage of raw crawled artifacts.

    This class handles:
    - Saving raw content (HTML, PDF, DOC, DOCX)
    - Writing metadata.json files
    - Computing content hashes
    - Creating backups for force refresh

    Directory structure:
        data/raw/{law_id}/
        ├── latest/
        │   ├── main.html
        │   ├── metadata.json
        │   └── attachments/
        └── crawls/
            └── {timestamp}/
                ├── main.html
                └── metadata.json

    Attributes:
        output_dir: Base directory for raw artifacts.
        crawler_version: Version string for the crawler.
    """

    def __init__(self, output_dir: str | Path, crawler_version: str = "v1.0.0"):
        """Initialize the artifact store.

        Args:
            output_dir: Base directory for raw artifacts.
            crawler_version: Version string for the crawler.
        """
        self.output_dir = Path(output_dir)
        self.crawler_version = crawler_version
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_law_dir(self, law_id: str) -> Path:
        """Get the directory for a specific law.

        Args:
            law_id: Unique law identifier.

        Returns:
            Path to the law's base directory.
        """
        return self.output_dir / law_id

    def get_latest_dir(self, law_id: str) -> Path:
        """Get the latest crawl directory for a law.

        Args:
            law_id: Unique law identifier.

        Returns:
            Path to the latest/ directory.
        """
        return self.get_law_dir(law_id) / "latest"

    def content_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of content.

        Args:
            data: Raw bytes to hash.

        Returns:
            SHA-256 hash as hexadecimal string.
        """
        return hashlib.sha256(data).hexdigest()

    def save_html(
        self,
        law_id: str,
        content: bytes,
        http_status: int | None = None,
        refresh: bool = False,
        previous_content_hash: str | None = None,
        **metadata_fields: Any,
    ) -> MetadataSchema:
        """Save HTML content and metadata.

        Args:
            law_id: Unique law identifier.
            content: Raw HTML content bytes.
            http_status: HTTP response status code.
            refresh: Whether this is a refresh crawl.
            previous_content_hash: Content hash from previous crawl.
            **metadata_fields: Additional metadata fields.

        Returns:
            MetadataSchema with saved metadata.

        Raises:
            StorageError: If saving fails.
        """
        latest_dir = self.get_latest_dir(law_id)

        if refresh and latest_dir.exists():
            self._create_backup(law_id)

        # Save HTML content
        html_path = latest_dir / "main.html"
        try:
            latest_dir.mkdir(parents=True, exist_ok=True)
            with open(html_path, "wb") as f:
                f.write(content)
        except OSError as e:
            raise StorageError(
                f"Failed to save HTML: {e}",
                path=str(html_path),
            ) from e

        # Compute content hash
        content_sha = self.content_hash(content)

        # Build metadata
        metadata = MetadataSchema(
            law_id=law_id,
            name=metadata_fields.get("name", ""),
            tier=metadata_fields.get("tier", 0),
            group=metadata_fields.get("group"),
            source_domain=metadata_fields.get("source_domain", "thuvienphapluat.vn"),
            source_type=metadata_fields.get("source_type", "html"),
            url=metadata_fields.get("url", ""),
            crawl_status="success",
            http_status=http_status,
            crawled_at=MetadataSchema.now_iso(),
            content_hash=content_sha,
            crawler_version=self.crawler_version,
            parser_hint=metadata_fields.get("parser_hint", "tvpl_html"),
            effective_date=metadata_fields.get("effective_date"),
            expiry_date=metadata_fields.get("expiry_date"),
            attachment_paths=metadata_fields.get("attachment_paths", []),
            refresh=refresh,
            previous_content_hash=previous_content_hash,
        )

        # Save metadata
        self.write_metadata(law_id, metadata)

        return metadata

    def save_attachment(
        self,
        law_id: str,
        content: bytes,
        filename: str,
    ) -> Path:
        """Save an attachment file (PDF, DOC, DOCX).

        Args:
            law_id: Unique law identifier.
            content: Raw attachment content bytes.
            filename: Name of the attachment file.

        Returns:
            Path to the saved attachment.

        Raises:
            StorageError: If saving fails.
        """
        attachments_dir = self.get_latest_dir(law_id) / "attachments"

        try:
            attachments_dir.mkdir(parents=True, exist_ok=True)
            attachment_path = attachments_dir / filename

            with open(attachment_path, "wb") as f:
                f.write(content)

            return attachment_path

        except OSError as e:
            raise StorageError(
                f"Failed to save attachment: {e}",
                path=str(attachment_path),
            ) from e

    def write_metadata(
        self,
        law_id: str,
        metadata: MetadataSchema,
    ) -> Path:
        """Write metadata.json file.

        Args:
            law_id: Unique law identifier.
            metadata: MetadataSchema to write.

        Returns:
            Path to the written metadata file.

        Raises:
            StorageError: If writing fails.
        """
        latest_dir = self.get_latest_dir(law_id)

        try:
            latest_dir.mkdir(parents=True, exist_ok=True)
            metadata_path = latest_dir / "metadata.json"

            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)

            return metadata_path

        except OSError as e:
            raise StorageError(
                f"Failed to write metadata: {e}",
                path=str(metadata_path),
            ) from e

    def _create_backup(self, law_id: str) -> Path:
        """Create a timestamped backup of existing crawl.

        Args:
            law_id: Unique law identifier.

        Returns:
            Path to the backup directory.
        """
        law_dir = self.get_law_dir(law_id)
        crawls_dir = law_dir / "crawls"

        # Generate timestamp
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
        backup_dir = crawls_dir / timestamp

        # Create crawls directory if needed
        crawls_dir.mkdir(parents=True, exist_ok=True)

        # Move latest to backup
        latest_dir = law_dir / "latest"
        if latest_dir.exists():
            try:
                shutil.move(str(latest_dir), str(backup_dir))
            except OSError as e:
                raise StorageError(
                    f"Failed to create backup: {e}",
                    path=str(backup_dir),
                )

        return backup_dir

    def metadata_exists(self, law_id: str) -> bool:
        """Check if metadata.json exists for a law.

        Args:
            law_id: Unique law identifier.

        Returns:
            True if metadata.json exists.
        """
        metadata_path = self.get_latest_dir(law_id) / "metadata.json"
        return metadata_path.exists()

    def load_metadata(self, law_id: str) -> MetadataSchema | None:
        """Load existing metadata for a law.

        Args:
            law_id: Unique law identifier.

        Returns:
            MetadataSchema if found, None otherwise.
        """
        metadata_path = self.get_latest_dir(law_id) / "metadata.json"

        if not metadata_path.exists():
            return None

        try:
            with open(metadata_path, encoding="utf-8") as f:
                data = json.load(f)

            return MetadataSchema(**data)

        except (json.JSONDecodeError, OSError):
            return None

    def ensure_output_dir(self) -> None:
        """Ensure the output directory exists.

        Raises:
            StorageError: If the directory cannot be created.
        """
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise StorageError(
                f"Failed to create output directory: {e}",
                path=str(self.output_dir),
            )
