from __future__ import annotations

from src.evaluation.benchmark.enums import (
    BenchmarkSplit,
    ExpectedDecision,
    LegalDomain,
    QuestionType,
)
from src.evaluation.benchmark.schemas import BenchmarkConfig, BenchmarkQuery
from src.evaluation.benchmark.splitting import create_grouped_split
from src.evaluation.benchmark.validator import official_duplicate_key


def _config(seed: int = 13) -> BenchmarkConfig:
    return BenchmarkConfig(
        schema_version="1.0",
        development_ratio=0.5,
        split_seed=seed,
        grouping_fields=["case_family_id", "source_provision_group_id"],
        stratification_fields=[
            "primary_domain",
            "expected_decision",
            "blocking",
            "question_types",
            "complete_evidence_required",
        ],
    )


def _query(query_id: str, **updates: object) -> BenchmarkQuery:
    payload = {
        "id": query_id,
        "query": f"Synthetic question {query_id}?",
        "primary_domain": LegalDomain.CIVIL_FAMILY_IDENTITY,
        "question_types": [QuestionType.SINGLE_ARTICLE_LOOKUP],
        "expected_decision": ExpectedDecision.ANSWER_ALLOWED,
        "reviewer_notes": "Synthetic fixture.",
    }
    payload.update(updates)
    return BenchmarkQuery.model_validate(payload)


def test_group_constraints_are_preserved() -> None:
    queries = [
        _query("a", case_family_id="fam1"),
        _query("b", case_family_id="fam1"),
        _query("c"),
    ]
    plan = create_grouped_split(queries, config=_config())
    assert plan.manifest.assignments["a"] == plan.manifest.assignments["b"]


def test_transitive_connected_groups_are_preserved() -> None:
    queries = [
        _query("a", case_family_id="fam1"),
        _query("b", case_family_id="fam1", source_provision_group_id="src1"),
        _query("c", source_provision_group_id="src1"),
        _query("d"),
    ]
    plan = create_grouped_split(queries, config=_config())
    split = plan.manifest.assignments["a"]
    assert plan.manifest.assignments["b"] == split
    assert plan.manifest.assignments["c"] == split


def test_same_seed_and_input_are_deterministic() -> None:
    queries = [_query("b"), _query("a"), _query("c")]
    left = create_grouped_split(queries, config=_config(seed=99))
    right = create_grouped_split(queries, config=_config(seed=99))
    assert left.manifest.assignments == right.manifest.assignments
    assert left.manifest.input_fingerprint == right.manifest.input_fingerprint


def test_stable_output_ordering() -> None:
    plan = create_grouped_split([_query("b"), _query("a")], config=_config())
    assert list(plan.manifest.assignments) == ["a", "b"]


def test_regression_overlap_is_forced_to_development() -> None:
    query = _query("reg", query="Known regression?")
    plan = create_grouped_split(
        [query, _query("other")],
        config=_config(),
        regression_query_texts={official_duplicate_key("Known regression?")},
    )
    assert plan.manifest.assignments["reg"] == BenchmarkSplit.DEVELOPMENT


def test_no_group_leakage() -> None:
    queries = [
        _query("a", source_provision_group_id="src"),
        _query("b", source_provision_group_id="src"),
    ]
    plan = create_grouped_split(queries, config=_config())
    assert len({plan.manifest.assignments[query.id] for query in queries}) == 1


def test_changed_input_changes_input_fingerprint() -> None:
    left = create_grouped_split([_query("a")], config=_config())
    right = create_grouped_split(
        [_query("a", query="Changed synthetic question?")], config=_config()
    )
    assert left.manifest.input_fingerprint != right.manifest.input_fingerprint


def test_input_fingerprint_is_stable_for_equivalent_query_ordering() -> None:
    left = create_grouped_split([_query("a"), _query("b")], config=_config())
    right = create_grouped_split([_query("b"), _query("a")], config=_config())
    assert left.manifest.input_fingerprint == right.manifest.input_fingerprint


def test_stratification_summary_is_reported() -> None:
    plan = create_grouped_split([_query("a"), _query("b")], config=_config())
    assert "primary_domain" in plan.stratification_summary
    assert plan.warnings
