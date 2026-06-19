"""Grouped deterministic split creation for legal QA benchmark records."""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.evaluation.benchmark.enums import BenchmarkSplit
from src.evaluation.benchmark.fingerprinting import sha256_records_by_stable_id
from src.evaluation.benchmark.schemas import BenchmarkConfig, BenchmarkQuery, SplitManifest
from src.evaluation.benchmark.validator import official_duplicate_key


class SplitComponent(BaseModel):
    """Connected query component that must remain in one split."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_ids: list[str]
    forced_split: BenchmarkSplit | None = None
    reasons: list[str] = Field(default_factory=list)


class SplitPlan(BaseModel):
    """Split assignments plus balance diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: SplitManifest
    components: list[SplitComponent]
    achieved_counts: dict[str, int]
    stratification_summary: dict[str, dict[str, int]]
    warnings: list[str] = Field(default_factory=list)


class _UnionFind:
    def __init__(self, values: list[str]) -> None:
        self.parent = {value: value for value in values}

    def find(self, value: str) -> str:
        parent = self.parent[value]
        if parent != value:
            self.parent[value] = self.find(parent)
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if root_left < root_right:
            self.parent[root_right] = root_left
        else:
            self.parent[root_left] = root_right


def create_grouped_split(
    queries: list[BenchmarkQuery],
    *,
    config: BenchmarkConfig,
    regression_query_texts: set[str] | None = None,
) -> SplitPlan:
    """Create a deterministic grouped development/held-out split.

    Args:
        queries: Benchmark queries to assign.
        config: Split configuration.
        regression_query_texts: Official-normalized existing regression query
            texts. Matching queries are forced to development.

    Returns:
        Deterministic split plan and manifest.

    Legal assumptions:
        Split creation does not inspect system performance. Regression-overlap
        cases are never assigned to held-out test.
    """
    if not queries:
        raise ValueError("cannot split an empty query set")
    regression_query_texts = regression_query_texts or set()
    ordered_queries = sorted(queries, key=lambda query: query.id)
    query_by_id = {query.id: query for query in ordered_queries}
    if len(query_by_id) != len(ordered_queries):
        raise ValueError("query IDs must be unique before splitting")

    union_find = _UnionFind([query.id for query in ordered_queries])
    for field_name in config.grouping_fields:
        _connect_by_field(ordered_queries, union_find, field_name)

    component_members: dict[str, list[str]] = defaultdict(list)
    for query in ordered_queries:
        component_members[union_find.find(query.id)].append(query.id)

    components = [
        _build_component(sorted(member_ids), query_by_id, regression_query_texts)
        for member_ids in component_members.values()
    ]
    components.sort(key=lambda component: component.query_ids)

    total_queries = len(ordered_queries)
    target_development = round(total_queries * config.development_ratio)
    assignments: dict[str, BenchmarkSplit] = {}
    assigned_development = 0

    for component in components:
        if component.forced_split == BenchmarkSplit.DEVELOPMENT:
            for query_id in component.query_ids:
                assignments[query_id] = BenchmarkSplit.DEVELOPMENT
            assigned_development += len(component.query_ids)

    remaining = [component for component in components if component.forced_split is None]
    rng = random.Random(config.split_seed)
    remaining.sort(
        key=lambda component: (
            rng.random(),
            "|".join(component.query_ids),
        ),
    )
    for component in remaining:
        if assigned_development < target_development:
            split = BenchmarkSplit.DEVELOPMENT
            assigned_development += len(component.query_ids)
        else:
            split = BenchmarkSplit.HELD_OUT_TEST
        for query_id in component.query_ids:
            assignments[query_id] = split

    stable_assignments = {query_id: assignments[query_id] for query_id in sorted(assignments)}
    warnings = _build_stratification_warnings(ordered_queries, stable_assignments, config)
    manifest = SplitManifest(
        schema_version=config.schema_version,
        benchmark_version=config.benchmark_version,
        strategy="connected_component_grouped_split",
        seed=config.split_seed,
        development_ratio=config.development_ratio,
        grouping_fields=config.grouping_fields,
        stratification_fields=config.stratification_fields,
        input_fingerprint=sha256_records_by_stable_id(
            ordered_queries,
            lambda record: record.id,
        ),
        assignments=stable_assignments,
        created_at=datetime.now(UTC),
        summary={
            "achieved_counts": _count_assignments(stable_assignments),
            "stratification_summary": _stratification_summary(
                ordered_queries,
                stable_assignments,
                config.stratification_fields,
            ),
            "warnings": warnings,
        },
    )
    return SplitPlan(
        manifest=manifest,
        components=components,
        achieved_counts=_count_assignments(stable_assignments),
        stratification_summary=_stratification_summary(
            ordered_queries,
            stable_assignments,
            config.stratification_fields,
        ),
        warnings=warnings,
    )


def _connect_by_field(
    queries: list[BenchmarkQuery], union_find: _UnionFind, field_name: str
) -> None:
    by_value: dict[str, list[str]] = defaultdict(list)
    for query in queries:
        value = getattr(query, field_name)
        if value:
            by_value[value].append(query.id)
    for query_ids in by_value.values():
        first = query_ids[0]
        for query_id in query_ids[1:]:
            union_find.union(first, query_id)


def _build_component(
    query_ids: list[str],
    query_by_id: dict[str, BenchmarkQuery],
    regression_query_texts: set[str],
) -> SplitComponent:
    reasons: list[str] = []
    for query_id in query_ids:
        query = query_by_id[query_id]
        if query.regression_case_ids:
            reasons.append(f"{query_id}: declared regression overlap")
        if official_duplicate_key(query.query) in regression_query_texts:
            reasons.append(f"{query_id}: exact normalized regression query match")
    forced = BenchmarkSplit.DEVELOPMENT if reasons else None
    return SplitComponent(query_ids=query_ids, forced_split=forced, reasons=sorted(reasons))


def _count_assignments(assignments: dict[str, BenchmarkSplit]) -> dict[str, int]:
    counts = Counter(split.value for split in assignments.values())
    return {
        BenchmarkSplit.DEVELOPMENT.value: counts[BenchmarkSplit.DEVELOPMENT.value],
        BenchmarkSplit.HELD_OUT_TEST.value: counts[BenchmarkSplit.HELD_OUT_TEST.value],
    }


def _stratification_summary(
    queries: list[BenchmarkQuery],
    assignments: dict[str, BenchmarkSplit],
    fields: list[str],
) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for field_name in fields:
        counts: Counter[str] = Counter()
        for query in queries:
            split = assignments[query.id].value
            value = _field_value(query, field_name)
            if isinstance(value, list):
                for item in value:
                    counts[f"{split}:{item}"] += 1
            else:
                counts[f"{split}:{value}"] += 1
        summary[field_name] = dict(sorted(counts.items()))
    return summary


def _field_value(query: BenchmarkQuery, field_name: str) -> Any:
    value = getattr(query, field_name)
    if isinstance(value, list):
        return [getattr(item, "value", str(item)) for item in value]
    if hasattr(value, "value"):
        return value.value
    return value


def _build_stratification_warnings(
    queries: list[BenchmarkQuery],
    assignments: dict[str, BenchmarkSplit],
    config: BenchmarkConfig,
) -> list[str]:
    warnings: list[str] = []
    if "question_types" in config.stratification_fields:
        warnings.append(
            "question_types is multi-label; summary is diagnostic and not a hard quota",
        )
    held_out_count = sum(
        1 for split in assignments.values() if split == BenchmarkSplit.HELD_OUT_TEST
    )
    if held_out_count == 0:
        warnings.append("held_out_test split is empty for this input size and grouping")
    if len(queries) < 10:
        warnings.append("small query count may produce poor stratification balance")
    return warnings
