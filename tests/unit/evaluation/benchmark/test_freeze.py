from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    EvidenceGroupRequirement,
    ExpectedDecision,
    LegalDomain,
    MatchLevel,
    QuestionType,
    RelevanceLevel,
    ReviewStage,
    ReviewStatus,
    TargetRole,
)
from src.evaluation.benchmark.exceptions import BenchmarkFreezeError
from src.evaluation.benchmark.fingerprinting import create_benchmark_manifest
from src.evaluation.benchmark.loader import BenchmarkFileSet
from src.evaluation.benchmark.schemas import BenchmarkConfig, SplitManifest
from src.indexing.official_artifacts import write_json_atomic


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _config(version: str = "benchmark_v1") -> BenchmarkConfig:
    return BenchmarkConfig(
        schema_version="1.0",
        benchmark_version=version,
        development_ratio=0.7,
        split_seed=1,
        grouping_fields=["case_family_id", "source_provision_group_id"],
    )


def _fixture(tmp_path: Path) -> tuple[BenchmarkFileSet, Path, Path, Path, Path]:
    queries = tmp_path / "queries.jsonl"
    targets = tmp_path / "targets.jsonl"
    judgments = tmp_path / "judgments.jsonl"
    groups = tmp_path / "groups.jsonl"
    reviews = tmp_path / "reviews.jsonl"
    split = tmp_path / "split.json"
    registry = tmp_path / "registry.yml"
    chunks = tmp_path / "chunks.jsonl"

    _write_jsonl(
        queries,
        [
            {
                "id": "q1",
                "query": "Synthetic freeze question?",
                "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY.value,
                "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP.value],
                "expected_decision": ExpectedDecision.ANSWER_ALLOWED.value,
                "review_status": ReviewStatus.FROZEN.value,
                "reviewer_notes": "Synthetic fixture.",
                "split": BenchmarkSplit.DEVELOPMENT.value,
            }
        ],
    )
    _write_jsonl(
        targets,
        [
            {
                "id": "t1",
                "query_id": "q1",
                "law_id": "LAW_A",
                "document_title": "Synthetic Law",
                "article_number": "1",
                "match_level": MatchLevel.ARTICLE.value,
                "target_role": TargetRole.REQUIRED.value,
            }
        ],
    )
    _write_jsonl(
        judgments,
        [
            {
                "query_id": "q1",
                "chunk_id": "chunk_1",
                "relevance": RelevanceLevel.REQUIRED_DIRECT.value,
                "evidence_group_ids": ["g1"],
            }
        ],
    )
    _write_jsonl(
        groups,
        [
            {
                "query_id": "q1",
                "evidence_group_id": "g1",
                "requirement": EvidenceGroupRequirement.REQUIRED.value,
                "minimum_hits": 1,
                "acceptable_chunk_ids": ["chunk_1"],
                "acceptable_legal_targets": [
                    {
                        "law_id": "LAW_A",
                        "article_number": "1",
                        "match_level": MatchLevel.ARTICLE.value,
                    }
                ],
            }
        ],
    )
    _write_jsonl(
        reviews,
        [
            {
                "id": "r1",
                "query_id": "q1",
                "review_stage": ReviewStage.PRIMARY_ANNOTATION.value,
                "reviewer_id": "reviewer_a",
                "status": ReviewStatus.PRIMARY_REVIEWED.value,
                "reviewed_fields": ["expected_decision"],
                "reviewed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            }
        ],
    )
    split_manifest = SplitManifest(
        schema_version="1.0",
        benchmark_version="benchmark_v1",
        strategy="connected_component_grouped_split",
        seed=1,
        development_ratio=0.7,
        grouping_fields=["case_family_id", "source_provision_group_id"],
        input_fingerprint="a" * 64,
        assignments={"q1": BenchmarkSplit.DEVELOPMENT},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    write_json_atomic(split, split_manifest.model_dump(mode="json"))
    registry.write_text("corpus:\n  - law_id: LAW_A\n", encoding="utf-8")
    _write_jsonl(
        chunks,
        [
            {
                "chunk_id": "chunk_1",
                "law_id": "LAW_A",
                "article_number": "1",
                "clause_number": None,
                "point_label": None,
                "level": "article",
            }
        ],
    )
    return (
        BenchmarkFileSet(
            queries=queries,
            legal_targets=targets,
            evidence_judgments=judgments,
            evidence_groups=groups,
            review_records=reviews,
        ),
        split,
        registry,
        chunks,
        tmp_path / "manifest.json",
    )


def _freeze(tmp_path: Path, *, config: BenchmarkConfig | None = None) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)
    create_benchmark_manifest(
        file_set=file_set,
        config=config or _config(),
        split_manifest_path=split,
        corpus_registry_path=registry,
        processed_chunks_path=chunks,
        output_path=output,
        change_log=["Synthetic freeze."],
    )


def test_freeze_refuses_draft_version(tmp_path: Path) -> None:
    with pytest.raises(BenchmarkFreezeError, match="release version"):
        _freeze(tmp_path, config=_config(version="draft"))


def test_freeze_refuses_existing_output(tmp_path: Path) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(BenchmarkFreezeError, match="overwrite"):
        create_benchmark_manifest(
            file_set=file_set,
            config=_config(),
            split_manifest_path=split,
            corpus_registry_path=registry,
            processed_chunks_path=chunks,
            output_path=output,
            change_log=["Synthetic freeze."],
        )


def test_freeze_refuses_missing_assignment(tmp_path: Path) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)
    manifest = json.loads(split.read_text(encoding="utf-8"))
    manifest["assignments"] = {}
    split.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(BenchmarkFreezeError, match="input loading failed"):
        create_benchmark_manifest(
            file_set=file_set,
            config=_config(),
            split_manifest_path=split,
            corpus_registry_path=registry,
            processed_chunks_path=chunks,
            output_path=output,
            change_log=["Synthetic freeze."],
        )


def test_freeze_refuses_query_split_mismatch(tmp_path: Path) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)
    manifest = json.loads(split.read_text(encoding="utf-8"))
    manifest["assignments"] = {"q1": BenchmarkSplit.HELD_OUT_TEST.value}
    split.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(BenchmarkFreezeError, match="validation has"):
        create_benchmark_manifest(
            file_set=file_set,
            config=_config(),
            split_manifest_path=split,
            corpus_registry_path=registry,
            processed_chunks_path=chunks,
            output_path=output,
            change_log=["Synthetic freeze."],
        )


def test_freeze_refuses_incomplete_review(tmp_path: Path) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)
    file_set.review_records.write_text("", encoding="utf-8")
    with pytest.raises(BenchmarkFreezeError, match="validation has"):
        create_benchmark_manifest(
            file_set=file_set,
            config=_config(),
            split_manifest_path=split,
            corpus_registry_path=registry,
            processed_chunks_path=chunks,
            output_path=output,
            change_log=["Synthetic freeze."],
        )


def test_freeze_refuses_unresolved_conflict(tmp_path: Path) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)
    _write_jsonl(
        file_set.review_records,
        [
            {
                "id": "r1",
                "query_id": "q1",
                "review_stage": ReviewStage.PRIMARY_ANNOTATION.value,
                "reviewer_id": "reviewer_a",
                "status": ReviewStatus.PRIMARY_REVIEWED.value,
                "reviewed_fields": ["expected_decision"],
                "reviewed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            },
            {
                "id": "r2",
                "query_id": "q1",
                "review_stage": ReviewStage.INDEPENDENT_REVIEW.value,
                "reviewer_id": "reviewer_b",
                "status": ReviewStatus.CONFLICT.value,
                "reviewed_fields": ["expected_decision"],
                "disagreements": ["expected_decision"],
                "reviewed_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            },
        ],
    )
    with pytest.raises(BenchmarkFreezeError, match="validation has"):
        create_benchmark_manifest(
            file_set=file_set,
            config=_config(),
            split_manifest_path=split,
            corpus_registry_path=registry,
            processed_chunks_path=chunks,
            output_path=output,
            change_log=["Synthetic freeze."],
        )


def test_freeze_detects_post_write_verification_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file_set, split, registry, chunks, output = _fixture(tmp_path)

    def _tampered_loader(path: Path) -> object:
        from src.evaluation.benchmark.loader import load_benchmark_manifest

        manifest = load_benchmark_manifest(path)
        return manifest.model_copy(update={"change_log": ["Tampered."]})

    monkeypatch.setattr(
        "src.evaluation.benchmark.fingerprinting.load_benchmark_manifest",
        _tampered_loader,
    )
    with pytest.raises(BenchmarkFreezeError, match="post-write"):
        create_benchmark_manifest(
            file_set=file_set,
            config=_config(),
            split_manifest_path=split,
            corpus_registry_path=registry,
            processed_chunks_path=chunks,
            output_path=output,
            change_log=["Synthetic freeze."],
        )


def test_successful_synthetic_freeze(tmp_path: Path) -> None:
    _freeze(tmp_path)
