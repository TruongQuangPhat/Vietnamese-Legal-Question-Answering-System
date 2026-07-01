"""Unit tests for the processed chunks deployment artifact fetcher."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.request import Request

import pytest

from scripts.deployment import fetch_processed_chunks


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _environment(tmp_path: Path, content: bytes) -> dict[str, str]:
    return {
        "LEGAL_QA_CHUNKS_URL": (
            "https://huggingface.example/datasets/repo/resolve/main/legal_chunks.jsonl"
        ),
        "LEGAL_QA_CHUNKS_SHA256": _sha256(content),
        "LEGAL_QA_CHUNKS_PATH": str(tmp_path / "nested" / "legal_chunks.jsonl"),
    }


def _downloader(content: bytes, calls: list[Request] | None = None):
    def download(request: Request, destination: Path) -> None:
        if calls is not None:
            calls.append(request)
        destination.write_bytes(content)

    return download


def test_missing_url_fails(tmp_path: Path) -> None:
    environment = _environment(tmp_path, b"chunks")
    environment.pop("LEGAL_QA_CHUNKS_URL")

    with pytest.raises(fetch_processed_chunks.ArtifactFetchError, match="URL is required"):
        fetch_processed_chunks.fetch_processed_chunks(
            environment,
            downloader=_downloader(b"chunks"),
        )


def test_missing_sha256_fails(tmp_path: Path) -> None:
    environment = _environment(tmp_path, b"chunks")
    environment.pop("LEGAL_QA_CHUNKS_SHA256")

    with pytest.raises(fetch_processed_chunks.ArtifactFetchError, match="SHA256 is required"):
        fetch_processed_chunks.fetch_processed_chunks(
            environment,
            downloader=_downloader(b"chunks"),
        )


def test_invalid_sha256_fails(tmp_path: Path) -> None:
    environment = _environment(tmp_path, b"chunks")
    environment["LEGAL_QA_CHUNKS_SHA256"] = "not-a-sha256"

    with pytest.raises(fetch_processed_chunks.ArtifactFetchError, match="64 hexadecimal"):
        fetch_processed_chunks.fetch_processed_chunks(
            environment,
            downloader=_downloader(b"chunks"),
        )


def test_successful_download_creates_parent_and_target(tmp_path: Path) -> None:
    content = b'{"chunk_id":"one"}\n'
    environment = _environment(tmp_path, content)
    target = Path(environment["LEGAL_QA_CHUNKS_PATH"])

    downloaded = fetch_processed_chunks.fetch_processed_chunks(
        environment,
        downloader=_downloader(content),
    )

    assert downloaded is True
    assert target.read_bytes() == content
    assert set(target.parent.iterdir()) == {target}


def test_default_target_matches_backend_chunks_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"default-path"
    environment = _environment(tmp_path, content)
    environment.pop("LEGAL_QA_CHUNKS_PATH")
    monkeypatch.chdir(tmp_path)

    fetch_processed_chunks.fetch_processed_chunks(
        environment,
        downloader=_downloader(content),
    )

    assert (tmp_path / "data/processed/legal_chunks.jsonl").read_bytes() == content


def test_checksum_mismatch_leaves_no_bad_final_file(tmp_path: Path) -> None:
    environment = _environment(tmp_path, b"expected")
    target = Path(environment["LEGAL_QA_CHUNKS_PATH"])

    with pytest.raises(fetch_processed_chunks.ArtifactFetchError, match="checksum mismatch"):
        fetch_processed_chunks.fetch_processed_chunks(
            environment,
            downloader=_downloader(b"wrong"),
        )

    assert not target.exists()
    assert list(target.parent.iterdir()) == []


def test_matching_existing_target_skips_download(tmp_path: Path) -> None:
    content = b"already-correct"
    environment = _environment(tmp_path, content)
    target = Path(environment["LEGAL_QA_CHUNKS_PATH"])
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    calls: list[Request] = []

    downloaded = fetch_processed_chunks.fetch_processed_chunks(
        environment,
        downloader=_downloader(b"must-not-write", calls),
    )

    assert downloaded is False
    assert calls == []
    assert target.read_bytes() == content


def test_mismatching_existing_target_fails_without_overwrite(tmp_path: Path) -> None:
    content = b"expected"
    environment = _environment(tmp_path, content)
    target = Path(environment["LEGAL_QA_CHUNKS_PATH"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing-wrong")
    calls: list[Request] = []

    with pytest.raises(fetch_processed_chunks.ArtifactFetchError, match="OVERWRITE=1"):
        fetch_processed_chunks.fetch_processed_chunks(
            environment,
            downloader=_downloader(content, calls),
        )

    assert calls == []
    assert target.read_bytes() == b"existing-wrong"


def test_explicit_overwrite_replaces_mismatching_target(tmp_path: Path) -> None:
    content = b"replacement"
    environment = _environment(tmp_path, content)
    environment["LEGAL_QA_CHUNKS_OVERWRITE"] = "1"
    target = Path(environment["LEGAL_QA_CHUNKS_PATH"])
    target.parent.mkdir(parents=True)
    target.write_bytes(b"existing-wrong")

    fetch_processed_chunks.fetch_processed_chunks(
        environment,
        downloader=_downloader(content),
    )

    assert target.read_bytes() == content


def test_output_does_not_include_url_query_or_hf_token(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    content = b"private-compatible"
    environment = _environment(tmp_path, content)
    environment["LEGAL_QA_CHUNKS_URL"] += "?download=true&token=url-secret"
    environment["HF_TOKEN"] = "hf-secret-value"
    captured_requests: list[Request] = []

    fetch_processed_chunks.fetch_processed_chunks(
        environment,
        downloader=_downloader(content, captured_requests),
    )

    output = capsys.readouterr()
    combined = output.out + output.err
    assert "download=true" not in combined
    assert "url-secret" not in combined
    assert "hf-secret-value" not in combined
    assert captured_requests[0].get_header("Authorization") == "Bearer hf-secret-value"


def test_download_failure_does_not_print_sensitive_url(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _environment(tmp_path, b"expected")
    environment["LEGAL_QA_CHUNKS_URL"] += "?signed=secret-query-value"
    monkeypatch.setattr(fetch_processed_chunks.os, "environ", environment)

    def fail_download(_request: Request, _destination: Path) -> None:
        raise OSError("network unavailable")

    monkeypatch.setattr(fetch_processed_chunks, "_download", fail_download)

    assert fetch_processed_chunks.main() == 1
    output = capsys.readouterr()
    assert "secret-query-value" not in output.err
    assert "signed=" not in output.err
