"""Fetch and verify the processed legal chunks artifact for deployment builds."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping
from http.client import HTTPException
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

DEFAULT_CHUNKS_PATH = Path("data/processed/legal_chunks.jsonl")
DOWNLOAD_TIMEOUT_SECONDS = 300
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class ArtifactFetchError(RuntimeError):
    """Raised when artifact configuration, download, or verification fails."""


Downloader = Callable[[Request, Path], None]


def fetch_processed_chunks(
    environment: Mapping[str, str],
    *,
    downloader: Downloader,
) -> bool:
    """Fetch the configured chunks artifact and atomically install it.

    Args:
        environment: Environment variable mapping containing artifact URL,
            SHA256, optional target path, overwrite flag, and optional HF token.
        downloader: Injected download boundary that writes the response body to
            the supplied temporary path.

    Returns:
        ``True`` when a new file is installed, or ``False`` when an existing
        file already matches the expected checksum.

    Raises:
        ArtifactFetchError: If configuration is missing/invalid, an existing
            target mismatches without explicit overwrite, download fails, or
            the downloaded checksum is invalid.
        OSError: If a filesystem operation fails.

    Side effects:
        Creates the target parent directory and may atomically replace the
        target only after checksum verification.
    """
    url = _required_value(environment, "LEGAL_QA_CHUNKS_URL")
    expected_sha256 = _required_value(environment, "LEGAL_QA_CHUNKS_SHA256").lower()
    if SHA256_PATTERN.fullmatch(expected_sha256) is None:
        raise ArtifactFetchError("LEGAL_QA_CHUNKS_SHA256 must contain 64 hexadecimal characters")

    raw_target = environment.get("LEGAL_QA_CHUNKS_PATH", "").strip()
    target = Path(raw_target) if raw_target else DEFAULT_CHUNKS_PATH
    overwrite = environment.get("LEGAL_QA_CHUNKS_OVERWRITE", "").strip() == "1"

    if target.exists():
        if _sha256(target) == expected_sha256:
            print(f"Processed chunks artifact already verified at {target}")
            return False
        if not overwrite:
            raise ArtifactFetchError(
                f"Existing processed chunks artifact checksum mismatch at {target}; "
                "set LEGAL_QA_CHUNKS_OVERWRITE=1 to replace it"
            )

    target.parent.mkdir(parents=True, exist_ok=True)
    source_label = _safe_source_label(url)
    request = _build_request(url, environment.get("HF_TOKEN"))
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        try:
            downloader(request, temporary_path)
        except (OSError, URLError, HTTPException) as exc:
            raise ArtifactFetchError(f"Artifact download failed from {source_label}") from exc

        actual_sha256 = _sha256(temporary_path)
        if actual_sha256 != expected_sha256:
            raise ArtifactFetchError(
                f"Downloaded processed chunks artifact checksum mismatch from {source_label}"
            )
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print(f"Processed chunks artifact verified and installed from {source_label} to {target}")
    return True


def _download(request: Request, destination: Path) -> None:
    """Download one request body to a temporary destination."""
    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
        with destination.open("wb") as output:
            shutil.copyfileobj(response, output)


def _build_request(url: str, raw_hf_token: str | None) -> Request:
    headers = {"User-Agent": "VnLaw-QA-artifact-fetch/1.0"}
    hf_token = raw_hf_token.strip() if raw_hf_token is not None else ""
    if hf_token:
        headers["Authorization"] = f"Bearer {hf_token}"
    try:
        return Request(url, headers=headers)
    except ValueError as exc:
        raise ArtifactFetchError("LEGAL_QA_CHUNKS_URL is invalid") from exc


def _required_value(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ArtifactFetchError(f"{name} is required")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for block in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_source_label(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or "unknown-host"
    filename = Path(unquote(parsed.path)).name or "artifact"
    return f"{hostname}/{filename}"


def main() -> int:
    """Run the deployment artifact fetch using process environment settings."""
    try:
        fetch_processed_chunks(os.environ, downloader=_download)
    except (ArtifactFetchError, OSError) as exc:
        print(f"Processed chunks artifact fetch failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
