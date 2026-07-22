"""Deterministic retrieval-quality benchmark and metric contracts.

This module evaluates direct-evidence retrieval, evidence selection, and prompt
citation mapping without calling an external LLM. It can run against another
checkout by importing that checkout's retrieval modules at execution time.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LABOR_LAW_ID = "BLLD_VBHN"
DEFAULT_CORPUS_PATH = Path("data/processed/legal_chunks.jsonl")
DIRECT_EVIDENCE_SCHEMA_VERSION = "2.1"
DIRECT_EVIDENCE_COMPARISON_SCHEMA_VERSION = "1.1"
DIRECT_EVIDENCE_METRIC_CONTRACT_VERSION = "direct_evidence_metrics_v1_runtime_cutoff"
RUNNER_EVALUATOR_VERSION = "retrieval_quality_generalization_v2_runtime_aligned"
DIRECT_EVIDENCE_CASE_SET_IDENTITY = "direct_evidence_generalization_v1"
DIRECT_EVIDENCE_MATCHING_GRANULARITY = "law_article_with_optional_clause_point"
DEFAULT_SPARSE_RETRIEVAL_TOP_K = 50
DEFAULT_DENSE_RETRIEVAL_TOP_K = 50
DEFAULT_DIAGNOSTIC_CANDIDATE_TOP_K = 50
DEFAULT_FUSION_OUTPUT_TOP_K = 10
DEFAULT_SELECTION_INPUT_TOP_K = 10
DEFAULT_SELECTED_EVIDENCE_BUDGET = 5
DEFAULT_CANDIDATE_TOP_K = DEFAULT_DIAGNOSTIC_CANDIDATE_TOP_K
DEFAULT_RECALL_DEPTHS = (5, 10)
DEFAULT_EVIDENCE_BUDGET = DEFAULT_SELECTED_EVIDENCE_BUDGET
REFERENCE_ONLY_PATTERN = re.compile(
    r"^(?:\d+\.|[a-zà-ỹđ]\))?\s*"
    r".{0,180}?\b(?:theo\s+quy\s+định\s+tại|thực\s+hiện\s+theo|thuộc\s+trường\s+hợp\s+"
    r"quy\s+định\s+tại|dẫn\s+chiếu\s+đến)\s+(?:điều|khoản)\s+\d+\b"
    r"(?:\s+của\s+bộ\s+luật\s+này)?\.?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BenchmarkRuntimeConfig:
    """Runtime and diagnostic candidate budgets used by the benchmark runner."""

    mode: str = "runtime_aligned"
    sparse_retrieval_top_k: int = DEFAULT_SPARSE_RETRIEVAL_TOP_K
    dense_retrieval_top_k: int = DEFAULT_DENSE_RETRIEVAL_TOP_K
    diagnostic_candidate_top_k: int = DEFAULT_DIAGNOSTIC_CANDIDATE_TOP_K
    fusion_output_top_k: int = DEFAULT_FUSION_OUTPUT_TOP_K
    selection_input_top_k: int = DEFAULT_SELECTION_INPUT_TOP_K
    selected_evidence_budget: int = DEFAULT_SELECTED_EVIDENCE_BUDGET
    production_aligned: bool = True

    @classmethod
    def for_mode(cls, mode: str) -> BenchmarkRuntimeConfig:
        """Return the named benchmark mode with production defaults."""
        if mode == "runtime_aligned":
            return cls(mode=mode, selection_input_top_k=DEFAULT_SELECTION_INPUT_TOP_K)
        if mode == "deep_diagnostic":
            return cls(
                mode=mode,
                selection_input_top_k=DEFAULT_DIAGNOSTIC_CANDIDATE_TOP_K,
                production_aligned=False,
            )
        raise ValueError(f"unsupported benchmark mode: {mode}")

    def with_overrides(
        self,
        *,
        sparse_retrieval_top_k: int | None = None,
        dense_retrieval_top_k: int | None = None,
        diagnostic_candidate_top_k: int | None = None,
        fusion_output_top_k: int | None = None,
        selection_input_top_k: int | None = None,
        selected_evidence_budget: int | None = None,
    ) -> BenchmarkRuntimeConfig:
        """Return a copy with validated explicit CLI overrides."""
        config = BenchmarkRuntimeConfig(
            mode=self.mode,
            sparse_retrieval_top_k=sparse_retrieval_top_k or self.sparse_retrieval_top_k,
            dense_retrieval_top_k=dense_retrieval_top_k or self.dense_retrieval_top_k,
            diagnostic_candidate_top_k=(
                diagnostic_candidate_top_k or self.diagnostic_candidate_top_k
            ),
            fusion_output_top_k=fusion_output_top_k or self.fusion_output_top_k,
            selection_input_top_k=selection_input_top_k or self.selection_input_top_k,
            selected_evidence_budget=selected_evidence_budget or self.selected_evidence_budget,
            production_aligned=(
                self.production_aligned
                and (selection_input_top_k or self.selection_input_top_k)
                == DEFAULT_SELECTION_INPUT_TOP_K
                and (fusion_output_top_k or self.fusion_output_top_k) == DEFAULT_FUSION_OUTPUT_TOP_K
                and (selected_evidence_budget or self.selected_evidence_budget)
                == DEFAULT_SELECTED_EVIDENCE_BUDGET
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate candidate budgets before any retrieval is executed."""
        values = {
            "sparse_retrieval_top_k": self.sparse_retrieval_top_k,
            "dense_retrieval_top_k": self.dense_retrieval_top_k,
            "diagnostic_candidate_top_k": self.diagnostic_candidate_top_k,
            "fusion_output_top_k": self.fusion_output_top_k,
            "selection_input_top_k": self.selection_input_top_k,
            "selected_evidence_budget": self.selected_evidence_budget,
        }
        for name, value in values.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.selection_input_top_k > self.diagnostic_candidate_top_k:
            raise ValueError("selection_input_top_k cannot exceed diagnostic_candidate_top_k")
        if self.selected_evidence_budget > self.selection_input_top_k:
            raise ValueError("selected_evidence_budget cannot exceed selection_input_top_k")

    def to_dict(self) -> dict[str, Any]:
        """Serialize benchmark mode and candidate budgets."""
        return {
            "benchmark_mode": self.mode,
            "sparse_retrieval_top_k": self.sparse_retrieval_top_k,
            "dense_retrieval_top_k": self.dense_retrieval_top_k,
            "diagnostic_candidate_top_k": self.diagnostic_candidate_top_k,
            "retrieval_candidate_limit": self.diagnostic_candidate_top_k,
            "fusion_output_top_k": self.fusion_output_top_k,
            "selection_input_top_k": self.selection_input_top_k,
            "selection_input_limit": self.selection_input_top_k,
            "selected_evidence_budget": self.selected_evidence_budget,
            "selected_evidence_limit": self.selected_evidence_budget,
            "production_aligned": self.production_aligned,
        }


@dataclass(frozen=True)
class DirectEvidenceReportMetadata:
    """Compatibility metadata for direct-evidence report comparison.

    Reports may be compared only when these fields describe the same metric
    contract, corpus, case set, evaluation stage, and runtime cutoff semantics.
    """

    schema_version: str
    metric_contract_version: str
    evaluator_version: str
    git_revision: str | None
    corpus_identity: str
    case_set_identity: str
    pipeline_family: str
    evaluation_stage: str
    retrieval_mode: str
    benchmark_mode: str
    matching_granularity: str
    cutoff_configuration: dict[str, Any]
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize report metadata for machine-readable envelopes."""
        return {
            "schema_version": self.schema_version,
            "metric_contract_version": self.metric_contract_version,
            "evaluator_version": self.evaluator_version,
            "runner_evaluator_version": self.evaluator_version,
            "git_revision": self.git_revision,
            "corpus_identity": self.corpus_identity,
            "corpus_identifier_or_path": self.corpus_identity,
            "case_set_identity": self.case_set_identity,
            "pipeline_family": self.pipeline_family,
            "evaluation_stage": self.evaluation_stage,
            "retrieval_mode": self.retrieval_mode,
            "benchmark_mode": self.benchmark_mode,
            "matching_granularity": self.matching_granularity,
            "cutoff_configuration": self.cutoff_configuration,
            "configuration": self.cutoff_configuration,
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class EvidenceTarget:
    """Expected legal locator for one benchmark assertion."""

    law_id: str
    article_number: str
    clause_number: str | None = None
    point_label: str | None = None
    role: str = "required"
    acceptable_alternatives: tuple[EvidenceTarget, ...] = ()
    forbidden_primary: bool = False
    forbidden_citation: bool = False

    def as_key(self) -> str:
        """Return a stable target key at the configured matching granularity."""
        parts = [self.law_id, f"Điều {self.article_number}"]
        if self.clause_number is not None:
            parts.append(f"Khoản {self.clause_number}")
        if self.point_label is not None:
            parts.append(f"Điểm {self.point_label}")
        return " / ".join(parts)

    def to_dict(self) -> dict[str, str | None]:
        """Serialize this target to JSON-compatible data."""
        return {
            "law_id": self.law_id,
            "article_number": self.article_number,
            "clause_number": self.clause_number,
            "point_label": self.point_label,
            "role": self.role,
            "acceptable_alternatives": [
                target.to_locator_dict() for target in self.acceptable_alternatives
            ],
            "forbidden_primary": self.forbidden_primary,
            "forbidden_citation": self.forbidden_citation,
            "matching_granularity": _target_granularity(self),
        }

    def to_locator_dict(self) -> dict[str, str | None]:
        """Serialize only the legal locator fields."""
        return {
            "law_id": self.law_id,
            "article_number": self.article_number,
            "clause_number": self.clause_number,
            "point_label": self.point_label,
        }


@dataclass(frozen=True)
class BenchmarkCase:
    """One deterministic direct-evidence benchmark case."""

    case_id: str
    query: str
    split: str
    intent: str
    expected_targets: tuple[EvidenceTarget, ...]
    primary_target: EvidenceTarget | None = None
    supporting_targets: tuple[EvidenceTarget, ...] = ()
    forbidden_primary_targets: tuple[EvidenceTarget, ...] = ()
    forbidden_citation_targets: tuple[EvidenceTarget, ...] = ()
    multi_target_all_required: bool = True
    forbid_labor_termination_articles: bool = False
    error_categories: tuple[str, ...] = field(default_factory=tuple)

    def required_targets(self) -> tuple[EvidenceTarget, ...]:
        """Return targets that must be selected and cited."""
        return tuple(
            target
            for target in (*self.expected_targets, *self.supporting_targets)
            if not target.forbidden_primary and not target.forbidden_citation
        )


@dataclass(frozen=True)
class CaseEvaluation:
    """Machine-readable diagnostics and pass/fail result for one case."""

    case_id: str
    query: str
    split: str
    intent: str
    expected_targets: tuple[EvidenceTarget, ...]
    primary_target: EvidenceTarget | None
    candidate_ranks: dict[str, int | None]
    selection_input_ranks: dict[str, int | None]
    selection_input_top_k: int
    selected_evidence: list[dict[str, Any]]
    prompt_evidence: list[dict[str, Any]]
    forbidden_selected: list[dict[str, Any]]
    forbidden_cited: list[dict[str, Any]]
    pass_status: bool
    pass_reason: str
    primary_evidence_accuracy: bool
    citation_alignment_accuracy: bool
    multi_article_coverage_accuracy: bool | None
    cross_reference_only_primary_error: bool
    wrong_actor_primary_error: bool
    wrong_domain_primary_error: bool

    def to_dict(self, *, recall_depths: Sequence[int]) -> dict[str, Any]:
        """Serialize this case with explicit per-depth candidate presence."""
        target_rows = []
        for target in self.expected_targets:
            key = target.as_key()
            rank = self.candidate_ranks.get(key)
            target_rows.append(
                {
                    **target.to_dict(),
                    "target_key": key,
                    "candidate_rank": rank,
                    "selection_input_rank": self.selection_input_ranks.get(key),
                    "available_to_selection": self.selection_input_ranks.get(key) is not None,
                    "selection_input_top_k": self.selection_input_top_k,
                    "candidate_presence": rank is not None,
                    "candidate_presence_by_depth": {
                        f"at_{depth}": rank is not None and rank <= depth for depth in recall_depths
                    },
                    "selected": any(
                        _summary_matches_target(item, target) for item in self.selected_evidence
                    ),
                    "cited": any(
                        _summary_matches_target(item, target) for item in self.prompt_evidence
                    ),
                    "role": "primary"
                    if self.primary_target is not None and target == self.primary_target
                    else "supporting",
                }
            )
        return {
            "case_id": self.case_id,
            "query": self.query,
            "split": self.split,
            "intent": self.intent,
            "expected_targets": target_rows,
            "primary_target": self.primary_target.to_dict()
            if self.primary_target is not None
            else None,
            "actual_primary_evidence": self.selected_evidence[0]
            if self.selected_evidence
            else None,
            "actual_primary_prompt_evidence": self.prompt_evidence[0]
            if self.prompt_evidence
            else None,
            "selected_provision_set": self.selected_evidence,
            "cited_provision_set": self.prompt_evidence,
            "forbidden_evidence_found": {
                "selected": self.forbidden_selected,
                "cited": self.forbidden_cited,
            },
            "primary_evidence_accuracy": self.primary_evidence_accuracy,
            "citation_alignment_accuracy": self.citation_alignment_accuracy,
            "cross_reference_only_primary_error": self.cross_reference_only_primary_error,
            "wrong_actor_primary_error": self.wrong_actor_primary_error,
            "wrong_domain_primary_error": self.wrong_domain_primary_error,
            "multi_article_coverage_accuracy": self.multi_article_coverage_accuracy,
            "pass": self.pass_status,
            "pass_reason": self.pass_reason,
        }


GOLDEN_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        case_id="employee_unilateral_termination",
        query="Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        split="development",
        intent="labor_employee_unilateral_termination",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "35"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "35"),
        error_categories=("wrong_actor_sensitive",),
    ),
    BenchmarkCase(
        case_id="employer_unilateral_termination",
        query="Người sử dụng lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        split="development",
        intent="labor_employer_unilateral_termination",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "36", "1"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "36", "1"),
        error_categories=("wrong_actor_sensitive",),
    ),
    BenchmarkCase(
        case_id="unlawful_unilateral_termination",
        query="Khi nào đơn phương chấm dứt hợp đồng lao động bị coi là trái pháp luật?",
        split="development",
        intent="labor_unlawful_unilateral_termination",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "39"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "39"),
    ),
    BenchmarkCase(
        case_id="employee_notice_period",
        query="Người lao động phải báo trước bao lâu khi đơn phương chấm dứt hợp đồng?",
        split="development",
        intent="labor_notice_period",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "35", "1"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "35", "1"),
        error_categories=("wrong_actor_sensitive",),
    ),
    BenchmarkCase(
        case_id="employee_no_notice",
        query="Người lao động có được nghỉ việc không cần báo trước trong trường hợp nào?",
        split="development",
        intent="labor_no_notice_exception",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "35", "2"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "35", "2"),
        error_categories=("wrong_actor_sensitive",),
    ),
)


OUT_OF_TOPIC_HOLDOUT_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        case_id="worker_maternity_return_notice",
        query=(
            "Khoản 4 Điều 139 Bộ luật Lao động quy định lao động nữ đi làm trước "
            "khi hết thời gian nghỉ thai sản phải báo trước thế nào?"
        ),
        split="holdout",
        intent="maternity_leave_notice",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "139", "4"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "139", "4"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="worker_weekly_rest",
        query="Khoản 1 Điều 111 Bộ luật Lao động quy định người lao động được nghỉ hằng tuần ít nhất bao lâu?",
        split="holdout",
        intent="weekly_rest",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "111", "1"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "111", "1"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="worker_annual_leave",
        query="Khoản 1 Điều 113 Bộ luật Lao động quy định người lao động nghỉ hằng năm bao nhiêu ngày?",
        split="holdout",
        intent="annual_leave",
        expected_targets=(EvidenceTarget(LABOR_LAW_ID, "113", "1"),),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "113", "1"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="civil_unlawful_transaction",
        query=(
            "Giao dịch dân sự trái pháp luật do vi phạm điều cấm của luật hoặc "
            "trái đạo đức xã hội theo Điều 123 Bộ luật Dân sự thế nào?"
        ),
        split="holdout",
        intent="civil_transaction_validity",
        expected_targets=(EvidenceTarget("BLDS_2015", "123"),),
        primary_target=EvidenceTarget("BLDS_2015", "123"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="civil_authorization_unilateral_termination",
        query=(
            "Khoản 1 Điều 569 Bộ luật Dân sự quy định bên ủy quyền đơn phương "
            "chấm dứt hợp đồng ủy quyền thế nào?"
        ),
        split="holdout",
        intent="civil_authorization_contract",
        expected_targets=(EvidenceTarget("BLDS_2015", "569", "1"),),
        primary_target=EvidenceTarget("BLDS_2015", "569", "1"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="marriage_age_condition",
        query=(
            "Điểm a khoản 1 Điều 8 Luật Hôn nhân và gia đình quy định điều kiện "
            "kết hôn về độ tuổi thế nào?"
        ),
        split="holdout",
        intent="marriage_conditions",
        expected_targets=(EvidenceTarget("LHNGD_VBHN", "8", "1", "a"),),
        primary_target=EvidenceTarget("LHNGD_VBHN", "8", "1", "a"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="land_user_common_rights",
        query="Khoản 1 Điều 26 Luật Đất đai quy định quyền chung của người sử dụng đất thế nào?",
        split="holdout",
        intent="land_user_rights",
        expected_targets=(EvidenceTarget("LDD_VBHN", "26", "1"),),
        primary_target=EvidenceTarget("LDD_VBHN", "26", "1"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="health_insurance_information_duty",
        query="Khoản 4 Điều 39 Luật Bảo hiểm y tế quy định trách nhiệm cung cấp thông tin thế nào?",
        split="holdout",
        intent="health_insurance_duties",
        expected_targets=(EvidenceTarget("LBHYT_VBHN", "39", "4"),),
        primary_target=EvidenceTarget("LBHYT_VBHN", "39", "4"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="notary_reporting_duty",
        query=(
            "Khoản 8 Điều 36 Luật Công chứng quy định nghĩa vụ báo cáo, kiểm tra, "
            "thanh tra thế nào?"
        ),
        split="holdout",
        intent="notary_organization_duties",
        expected_targets=(EvidenceTarget("LCCONGCHUNG_VBHN", "36", "8"),),
        primary_target=EvidenceTarget("LCCONGCHUNG_VBHN", "36", "8"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="notary_cross_reference_direct_target",
        query=(
            "Khoản 5 Điều 36 Luật Công chứng quy định nghĩa vụ mua bảo hiểm "
            "trách nhiệm nghề nghiệp của tổ chức hành nghề công chứng thế nào?"
        ),
        split="holdout",
        intent="direct_cross_reference_target",
        expected_targets=(EvidenceTarget("LCCONGCHUNG_VBHN", "36", "5"),),
        primary_target=EvidenceTarget("LCCONGCHUNG_VBHN", "36", "5"),
        forbid_labor_termination_articles=True,
    ),
    BenchmarkCase(
        case_id="weekly_and_annual_leave_multi_article",
        query=(
            "Khoản 1 Điều 111 và Khoản 1 Điều 113 Bộ luật Lao động quy định nghỉ "
            "hằng tuần và nghỉ hằng năm thế nào?"
        ),
        split="holdout",
        intent="multi_article_leave_coverage",
        expected_targets=(
            EvidenceTarget(LABOR_LAW_ID, "111", "1"),
            EvidenceTarget(LABOR_LAW_ID, "113", "1"),
        ),
        primary_target=EvidenceTarget(LABOR_LAW_ID, "111", "1"),
        forbid_labor_termination_articles=True,
    ),
)


BROAD_CROSS_DOMAIN_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        case_id="constitutional_human_rights",
        query="Khoản 1 Điều 14 Hiến pháp quy định quyền con người, quyền công dân thế nào?",
        split="holdout",
        intent="constitutional_rights",
        expected_targets=(EvidenceTarget("HP_2013", "14", "1"),),
        primary_target=EvidenceTarget("HP_2013", "14", "1"),
    ),
    BenchmarkCase(
        case_id="criminal_code_crime_definition",
        query="Khoản 1 Điều 8 Bộ luật Hình sự quy định khái niệm tội phạm thế nào?",
        split="holdout",
        intent="criminal_definition",
        expected_targets=(EvidenceTarget("BLHS_VBHN", "8", "1"),),
        primary_target=EvidenceTarget("BLHS_VBHN", "8", "1"),
    ),
    BenchmarkCase(
        case_id="civil_procedure_litigant_duty",
        query="Khoản 1 Điều 70 Bộ luật Tố tụng dân sự quy định nghĩa vụ của đương sự thế nào?",
        split="holdout",
        intent="civil_procedure_actor_duty",
        expected_targets=(EvidenceTarget("BLTTDS_VBHN", "70", "1"),),
        primary_target=EvidenceTarget("BLTTDS_VBHN", "70", "1"),
        error_categories=("wrong_actor_sensitive",),
    ),
    BenchmarkCase(
        case_id="criminal_procedure_accused_definition",
        query="Khoản 1 Điều 60 Bộ luật Tố tụng hình sự quy định bị can là ai?",
        split="holdout",
        intent="criminal_procedure_actor_definition",
        expected_targets=(EvidenceTarget("BLTTHS_VBHN", "60", "1"),),
        primary_target=EvidenceTarget("BLTTHS_VBHN", "60", "1"),
        error_categories=("wrong_actor_sensitive",),
    ),
    BenchmarkCase(
        case_id="food_safety_prohibited_act",
        query="Khoản 1 Điều 5 Luật An toàn thực phẩm quy định hành vi bị cấm nào?",
        split="holdout",
        intent="prohibition",
        expected_targets=(EvidenceTarget("LATTP_VBHN", "5", "1"),),
        primary_target=EvidenceTarget("LATTP_VBHN", "5", "1"),
    ),
    BenchmarkCase(
        case_id="environment_protection_principle",
        query="Khoản 1 Điều 4 Luật Bảo vệ môi trường quy định nguyên tắc bảo vệ môi trường thế nào?",
        split="holdout",
        intent="environment_principle",
        expected_targets=(EvidenceTarget("LBVMT_VBHN", "4", "1"),),
        primary_target=EvidenceTarget("LBVMT_VBHN", "4", "1"),
    ),
    BenchmarkCase(
        case_id="enterprise_business_right",
        query="Khoản 1 Điều 7 Luật Doanh nghiệp quy định quyền tự do kinh doanh thế nào?",
        split="holdout",
        intent="enterprise_permission",
        expected_targets=(EvidenceTarget("LDN_VBHN", "7", "1"),),
        primary_target=EvidenceTarget("LDN_VBHN", "7", "1"),
    ),
    BenchmarkCase(
        case_id="commerce_sale_contract_form",
        query="Khoản 1 Điều 24 Luật Thương mại quy định hình thức hợp đồng mua bán hàng hóa thế nào?",
        split="holdout",
        intent="commerce_contract_form",
        expected_targets=(EvidenceTarget("LTM_VBHN", "24", "1"),),
        primary_target=EvidenceTarget("LTM_VBHN", "24", "1"),
    ),
    BenchmarkCase(
        case_id="ip_right_definition",
        query="Khoản 1 Điều 4 Luật Sở hữu trí tuệ giải thích quyền sở hữu trí tuệ là gì?",
        split="holdout",
        intent="intellectual_property_definition",
        expected_targets=(EvidenceTarget("LSHTT_VBHN", "4", "1"),),
        primary_target=EvidenceTarget("LSHTT_VBHN", "4", "1"),
    ),
    BenchmarkCase(
        case_id="housing_owner_right_point",
        query="Điểm a khoản 1 Điều 10 Luật Nhà ở quy định quyền bất khả xâm phạm về nhà ở thế nào?",
        split="holdout",
        intent="housing_owner_right",
        expected_targets=(EvidenceTarget("LNO_VBHN", "10", "1", "a"),),
        primary_target=EvidenceTarget("LNO_VBHN", "10", "1", "a"),
    ),
    BenchmarkCase(
        case_id="taxpayer_support_right",
        query="Khoản 1 Điều 16 Luật Quản lý thuế quy định quyền được hỗ trợ của người nộp thuế thế nào?",
        split="holdout",
        intent="taxpayer_right",
        expected_targets=(EvidenceTarget("LQLT_VBHN", "16", "1"),),
        primary_target=EvidenceTarget("LQLT_VBHN", "16", "1"),
    ),
    BenchmarkCase(
        case_id="traffic_general_rule",
        query="Khoản 1 Điều 10 Luật Trật tự, an toàn giao thông đường bộ quy định quy tắc đi bên phải thế nào?",
        split="holdout",
        intent="traffic_rule",
        expected_targets=(EvidenceTarget("LTATGT_VBHN", "10", "1"),),
        primary_target=EvidenceTarget("LTATGT_VBHN", "10", "1"),
    ),
    BenchmarkCase(
        case_id="employment_state_management_point",
        query="Điểm a khoản 1 Điều 6 Luật Việc làm quy định ban hành văn bản về việc làm thế nào?",
        split="holdout",
        intent="employment_state_management",
        expected_targets=(EvidenceTarget("LVL_2025", "6", "1", "a"),),
        primary_target=EvidenceTarget("LVL_2025", "6", "1", "a"),
    ),
    BenchmarkCase(
        case_id="citizen_id_card_holder",
        query="Khoản 1 Điều 19 Luật Căn cước quy định người được cấp thẻ căn cước là ai?",
        split="holdout",
        intent="identity_card_holder",
        expected_targets=(EvidenceTarget("LCC_VBHN", "19", "1"),),
        primary_target=EvidenceTarget("LCC_VBHN", "19", "1"),
        error_categories=("wrong_actor_sensitive",),
    ),
)


BENCHMARK_CASES: tuple[BenchmarkCase, ...] = (
    *GOLDEN_CASES,
    *OUT_OF_TOPIC_HOLDOUT_CASES,
    *BROAD_CROSS_DOMAIN_CASES,
)


def run_sparse_selection_benchmark(
    *,
    repo_root: Path,
    corpus_path: Path,
    mode: str = "runtime_aligned",
    sparse_retrieval_top_k: int | None = None,
    dense_retrieval_top_k: int | None = None,
    diagnostic_candidate_top_k: int | None = None,
    fusion_output_top_k: int | None = None,
    selection_input_top_k: int | None = None,
    selected_evidence_budget: int | None = None,
    candidate_top_k: int | None = None,
    evidence_budget: int | None = None,
    recall_depths: Sequence[int] = DEFAULT_RECALL_DEPTHS,
) -> dict[str, Any]:
    """Run the benchmark against one checkout's sparse/selection pipeline.

    Metric definitions:
        Target matching is exact at the most specific locator present in the
        target: law ID and Article are always required; Clause and Point are
        required when supplied. Recall@k is micro-averaged over expected targets
        at candidate depth ``k``. Expected Article MRR is the mean reciprocal
        rank of the best expected target per case. Multi-target coverage
        requires every expected target to be selected and cited. Citation
        alignment requires all expected targets in prompt evidence and the
        primary prompt evidence to match the primary target when defined.
        Regression counting is performed only by ``compare_reports``.
    """
    if candidate_top_k is not None and diagnostic_candidate_top_k is None:
        diagnostic_candidate_top_k = candidate_top_k
    if evidence_budget is not None and selected_evidence_budget is None:
        selected_evidence_budget = evidence_budget
    runtime_config = BenchmarkRuntimeConfig.for_mode(mode).with_overrides(
        sparse_retrieval_top_k=sparse_retrieval_top_k,
        dense_retrieval_top_k=dense_retrieval_top_k,
        diagnostic_candidate_top_k=diagnostic_candidate_top_k,
        fusion_output_top_k=fusion_output_top_k,
        selection_input_top_k=selection_input_top_k,
        selected_evidence_budget=selected_evidence_budget,
    )
    _install_target_repo(repo_root)
    modules = _load_target_pipeline_modules()
    context_config = modules["ContextAssemblyConfig"](
        max_packets=runtime_config.selection_input_top_k
    )
    selection_config = modules["EvidenceSelectionConfig"](
        max_selected_packets=runtime_config.selected_evidence_budget
    )
    retriever = modules["SparseBM25Retriever"].from_jsonl(
        corpus_path,
        default_top_k=runtime_config.sparse_retrieval_top_k,
    )

    async def _run_all() -> list[CaseEvaluation]:
        results = []
        for case in BENCHMARK_CASES:
            results.append(
                await _evaluate_case(
                    case,
                    retriever=retriever,
                    modules=modules,
                    context_config=context_config,
                    selection_config=selection_config,
                    runtime_config=runtime_config,
                )
            )
        return results

    cases = asyncio.run(_run_all())
    per_case = [case.to_dict(recall_depths=recall_depths) for case in cases]
    metadata = build_report_metadata(
        git_revision=_git_revision(repo_root),
        corpus_identity=str(corpus_path),
        pipeline_family="direct_evidence",
        evaluation_stage="sparse_selection_diagnostic",
        retrieval_mode="sparse_selection",
        runtime_config=runtime_config,
        warnings=(),
        limitations=("deterministic sparse diagnostics do not load BGE-M3 or query Qdrant",),
    )
    report = {
        "benchmark_id": "retrieval_quality_generalization",
        "repo_root": str(repo_root),
        "production_aligned": runtime_config.production_aligned,
        "retrieval_candidate_limit": runtime_config.diagnostic_candidate_top_k,
        "selection_input_limit": runtime_config.selection_input_top_k,
        "selected_evidence_limit": runtime_config.selected_evidence_budget,
        "metric_definitions": metric_definitions(),
        "case_count": len(per_case),
        "case_splits": _split_counts(BENCHMARK_CASES),
        "aggregate_metrics": compute_aggregate_metrics(per_case, recall_depths=recall_depths),
        "cases": per_case,
    }
    report.update(metadata.to_dict())
    report["configuration"] = {
        **report["configuration"],
        "candidate_top_k": runtime_config.diagnostic_candidate_top_k,
        "recall_depths": list(recall_depths),
        "evidence_budget": runtime_config.selected_evidence_budget,
        "context_max_packets": runtime_config.selection_input_top_k,
        "selection_max_selected_packets": runtime_config.selected_evidence_budget,
        "prompt_mapping": "selected_evidence_order",
    }
    report["cutoff_configuration"] = dict(report["configuration"])
    report["corpus_path"] = str(corpus_path)
    return report


def metric_definitions() -> dict[str, str]:
    """Return the documented metric contracts used by this benchmark."""
    return {
        "recall_at_5": (
            "retrieval metric: micro-averaged expected-target recall at candidate rank <= 5 "
            "inside the full diagnostic retrieval pool; "
            "denominator is total expected targets, so a multi-article case contributes "
            "one denominator item per expected provision"
        ),
        "recall_at_10": (
            "retrieval metric: micro-averaged expected-target recall at candidate rank <= 10 "
            "inside the full diagnostic retrieval pool; denominator is total expected targets"
        ),
        "expected_article_mrr": (
            "retrieval metric: macro-averaged per-question reciprocal rank using the "
            "best-ranked expected target in the full diagnostic retrieval pool; cases "
            "with no expected target candidate contribute 0"
        ),
        "primary_evidence_accuracy": (
            "selection metric: macro-averaged fraction of cases where selected_evidence[0] "
            "exactly matches primary_target after truncating to the configured selection "
            "input limit"
        ),
        "citation_alignment_accuracy": (
            "selection metric: macro-averaged fraction of cases where prompt evidence built "
            "from selected evidence cites every expected target and prompt.evidence[0] "
            "matches primary_target when present"
        ),
        "cross_reference_only_primary_error_rate": (
            "macro-averaged fraction of cases where the selected primary is a generic "
            "reference-only provision that is not itself the expected primary target"
        ),
        "wrong_actor_primary_error_rate": (
            "macro-averaged fraction of actor-sensitive cases whose selected primary "
            "does not match the expected primary target"
        ),
        "wrong_domain_primary_error_rate": (
            "macro-averaged fraction of cases where selected primary law_id differs "
            "from primary_target.law_id"
        ),
        "multi_article_coverage_accuracy": (
            "macro-averaged over cases with more than one expected target; every expected "
            "target must be selected and cited"
        ),
        "regression_count": (
            "count of case-level semantic regressions plus expected-target candidate "
            "rank losses, including still-passing cases"
        ),
        "exact_matching_granularity": (
            "law_id + article_number are mandatory; clause_number and point_label "
            "are mandatory only when present in the expected target"
        ),
        "article_level_expectations": (
            "an expected target with clause_number=None and point_label=None matches any "
            "candidate/selected/cited provision in the same law and article"
        ),
        "multiple_acceptable_clauses": (
            "represented as an article-level target when the benchmark intent accepts "
            "multiple clauses in the same article; otherwise enumerate each required "
            "clause as a separate expected target"
        ),
        "candidate_depth": (
            "candidate ranks, Recall@5, Recall@10, Expected Article MRR, and rank "
            "regressions are measured against the top-50 diagnostic retrieval pool by default"
        ),
        "evidence_selection_input_budget": (
            "runtime_aligned mode builds evidence packets, selected evidence, and prompt "
            "citations from the top-10 selection input; deep_diagnostic mode may use up "
            "to the top-50 diagnostic pool and is not production-aligned"
        ),
        "single_target_scoring": (
            "primary evidence and first prompt evidence must match the primary target"
        ),
        "multi_target_coverage": (
            "all expected targets must be present in selected evidence and prompt citations "
            "after selection-input truncation; a multi-article case fails coverage when "
            "any required target is outside the selection input even if Recall@10 or "
            "diagnostic Recall@50 would find it"
        ),
        "regression_counting": (
            "semantic regressions are pass-to-fail, primary/citation/multi-target losses, "
            "wrong-domain increases, wrong-actor increases, or cross-reference-only "
            "primary errors; rank regressions are expected-target candidate ranks that "
            "move lower or disappear"
        ),
        "rank_regression_definition": (
            "an expected target rank regression occurs when the same target moves to a "
            "larger diagnostic-pool rank or disappears"
        ),
        "semantic_regression_definition": (
            "a semantic regression is a lost pass, primary-evidence loss, citation-alignment "
            "loss, multi-target coverage loss, or new wrong-actor/wrong-domain/"
            "cross-reference-only primary error"
        ),
    }


def compute_aggregate_metrics(
    cases: Sequence[dict[str, Any]],
    *,
    recall_depths: Sequence[int] = DEFAULT_RECALL_DEPTHS,
) -> dict[str, Any]:
    """Compute aggregate metrics from per-case JSON rows."""
    total_cases = len(cases)
    total_targets = sum(len(case["expected_targets"]) for case in cases)
    metrics: dict[str, Any] = {"total_cases": total_cases, "total_expected_targets": total_targets}

    for depth in recall_depths:
        found = sum(
            1
            for case in cases
            for target in case["expected_targets"]
            if target["candidate_rank"] is not None and target["candidate_rank"] <= depth
        )
        metrics[f"expected_evidence_recall_at_{depth}"] = _safe_div(found, total_targets)

    reciprocal_ranks = []
    for case in cases:
        ranks = [
            target["candidate_rank"]
            for target in case["expected_targets"]
            if target["candidate_rank"] is not None
        ]
        reciprocal_ranks.append((1 / min(ranks)) if ranks else 0.0)

    multi_article_cases = [
        case for case in cases if case["multi_article_coverage_accuracy"] is not None
    ]
    metrics.update(
        {
            "expected_article_mrr": _safe_div(sum(reciprocal_ranks), total_cases),
            "primary_evidence_accuracy": _case_rate(cases, "primary_evidence_accuracy"),
            "citation_alignment_accuracy": _case_rate(cases, "citation_alignment_accuracy"),
            "cross_reference_only_primary_error_rate": _case_rate(
                cases,
                "cross_reference_only_primary_error",
            ),
            "wrong_actor_primary_error_rate": _case_rate(cases, "wrong_actor_primary_error"),
            "wrong_domain_primary_error_rate": _case_rate(cases, "wrong_domain_primary_error"),
            "multi_article_coverage_accuracy": _case_rate(
                multi_article_cases,
                "multi_article_coverage_accuracy",
            ),
            "pass_rate": _safe_div(sum(1 for case in cases if case["pass"]), total_cases),
            "failed_case_count": sum(1 for case in cases if not case["pass"]),
            "regression_count": None,
        }
    )
    return metrics


def build_report_metadata(
    *,
    git_revision: str | None,
    corpus_identity: str,
    pipeline_family: str,
    evaluation_stage: str,
    retrieval_mode: str,
    runtime_config: BenchmarkRuntimeConfig,
    case_set_identity: str = DIRECT_EVIDENCE_CASE_SET_IDENTITY,
    evaluator_version: str = RUNNER_EVALUATOR_VERSION,
    schema_version: str = DIRECT_EVIDENCE_SCHEMA_VERSION,
    metric_contract_version: str = DIRECT_EVIDENCE_METRIC_CONTRACT_VERSION,
    matching_granularity: str = DIRECT_EVIDENCE_MATCHING_GRANULARITY,
    warnings: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> DirectEvidenceReportMetadata:
    """Build canonical direct-evidence report metadata."""
    return DirectEvidenceReportMetadata(
        schema_version=schema_version,
        metric_contract_version=metric_contract_version,
        evaluator_version=evaluator_version,
        git_revision=git_revision,
        corpus_identity=corpus_identity,
        case_set_identity=case_set_identity,
        pipeline_family=pipeline_family,
        evaluation_stage=evaluation_stage,
        retrieval_mode=retrieval_mode,
        benchmark_mode=runtime_config.mode,
        matching_granularity=matching_granularity,
        cutoff_configuration=runtime_config.to_dict(),
        warnings=tuple(warnings),
        limitations=tuple(limitations),
    )


def validate_report_compatibility(
    before: dict[str, Any],
    after: dict[str, Any],
    *,
    allow_diagnostic_mode_mismatch: bool = False,
) -> None:
    """Reject direct-evidence report comparison when contracts differ.

    Args:
        before: Baseline report envelope.
        after: Candidate report envelope.
        allow_diagnostic_mode_mismatch: Reserved escape hatch for future
            explicitly diagnostic comparisons. The default rejects
            runtime-aligned versus deep-diagnostic reports.

    Raises:
        ValueError: If any required compatibility field differs.
    """
    fields = (
        "schema_version",
        "metric_contract_version",
        "corpus_identity",
        "case_set_identity",
        "matching_granularity",
        "pipeline_family",
        "evaluation_stage",
        "retrieval_mode",
    )
    mismatches = [field for field in fields if before.get(field) != after.get(field)]
    before_cutoffs = before.get("cutoff_configuration") or before.get("configuration") or {}
    after_cutoffs = after.get("cutoff_configuration") or after.get("configuration") or {}
    cutoff_fields = (
        "diagnostic_candidate_top_k",
        "fusion_output_top_k",
        "selection_input_top_k",
        "selected_evidence_budget",
    )
    for cutoff_field in cutoff_fields:
        if before_cutoffs.get(cutoff_field) != after_cutoffs.get(cutoff_field):
            mismatches.append(f"cutoff_configuration.{cutoff_field}")
    if not allow_diagnostic_mode_mismatch and before.get("benchmark_mode") != after.get(
        "benchmark_mode"
    ):
        mismatches.append("benchmark_mode")
    if mismatches:
        joined = ", ".join(mismatches)
        raise ValueError(f"incompatible direct-evidence reports: {joined}")


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two benchmark reports and list every case-level regression."""
    validate_report_compatibility(before, after)
    before_cases = {case["case_id"]: case for case in before["cases"]}
    after_cases = {case["case_id"]: case for case in after["cases"]}
    if before_cases.keys() != after_cases.keys():
        raise ValueError("incompatible direct-evidence reports: case_id set differs")
    regressions: list[dict[str, Any]] = []
    improvements = 0
    unchanged = 0

    for case_id, before_case in before_cases.items():
        after_case = after_cases[case_id]
        case_regressions = _case_regressions(before_case, after_case)
        if case_regressions:
            regressions.extend(case_regressions)
        elif _case_improved(before_case, after_case):
            improvements += 1
        else:
            unchanged += 1

    before_rank_by_target = _target_ranks(before["cases"])
    after_rank_by_target = _target_ranks(after["cases"])
    rank_changes = [
        before_rank - after_rank
        for key, before_rank in before_rank_by_target.items()
        for after_rank in [after_rank_by_target.get(key)]
        if before_rank is not None and after_rank is not None
    ]

    return {
        "schema_version": DIRECT_EVIDENCE_COMPARISON_SCHEMA_VERSION,
        "metric_contract_version": after["metric_contract_version"],
        "evaluator_version": after["evaluator_version"],
        "benchmark_id": after["benchmark_id"],
        "case_set_identity": after["case_set_identity"],
        "corpus_identity": after["corpus_identity"],
        "pipeline_family": after["pipeline_family"],
        "evaluation_stage": after["evaluation_stage"],
        "retrieval_mode": after["retrieval_mode"],
        "benchmark_mode": after["benchmark_mode"],
        "matching_granularity": after["matching_granularity"],
        "cutoff_configuration": after.get("cutoff_configuration") or after["configuration"],
        "before": {
            "repo_root": before.get("repo_root"),
            "git_revision": before.get("git_revision"),
            "aggregate_metrics": before["aggregate_metrics"],
        },
        "after": {
            "repo_root": after.get("repo_root"),
            "git_revision": after.get("git_revision"),
            "aggregate_metrics": {
                **after["aggregate_metrics"],
                "regression_count": len(regressions),
            },
        },
        "regressions": regressions,
        "regression_count": len(regressions),
        "semantic_regression_count": sum(
            1 for regression in regressions if regression["type"] != "candidate_rank_loss"
        ),
        "rank_regression_count": sum(
            1 for regression in regressions if regression["type"] == "candidate_rank_loss"
        ),
        "improved_case_count": improvements,
        "unchanged_case_count": unchanged,
        "largest_positive_rank_change": max(rank_changes) if rank_changes else 0,
        "largest_negative_rank_change": min(rank_changes) if rank_changes else 0,
    }


async def _evaluate_case(
    case: BenchmarkCase,
    *,
    retriever: Any,
    modules: dict[str, Any],
    context_config: Any,
    selection_config: Any,
    runtime_config: BenchmarkRuntimeConfig,
) -> CaseEvaluation:
    retrieval = await retriever.retrieve(
        case.query,
        top_k=runtime_config.diagnostic_candidate_top_k,
    )
    selection_retrieval = _selection_input_retrieval(
        retrieval,
        selection_input_top_k=runtime_config.selection_input_top_k,
    )
    bundle = modules["build_evidence_bundle"](selection_retrieval, config=context_config)
    selection = modules["select_evidence_for_answer"](bundle, config=selection_config)
    prompt_evidence: list[Any] = []
    if selection.selected_evidence:
        prompt = modules["build_naive_rag_prompt"](query=case.query, selection_result=selection)
        prompt_evidence = list(prompt.evidence)

    selected_summaries = [
        _provision_summary(item.packet, item.rank) for item in selection.selected_evidence
    ]
    prompt_summaries = [
        _provision_summary(item, index) for index, item in enumerate(prompt_evidence, start=1)
    ]
    candidate_ranks = {
        target.as_key(): _target_rank(retrieval.results, target) for target in case.expected_targets
    }
    selection_input_ranks = {
        target.as_key(): _target_rank(selection_retrieval.results, target)
        for target in case.expected_targets
    }

    primary_ok = (
        case.primary_target is not None
        and bool(selection.selected_evidence)
        and _object_matches_target(selection.selected_evidence[0].packet, case.primary_target)
    )
    citation_ok = all(
        any(_object_matches_target(item, target) for item in prompt_evidence)
        for target in case.expected_targets
    ) and (
        case.primary_target is None
        or (
            bool(prompt_evidence)
            and _object_matches_target(prompt_evidence[0], case.primary_target)
        )
    )
    selected_coverage_ok = all(
        any(_object_matches_target(item.packet, target) for item in selection.selected_evidence)
        for target in case.expected_targets
    )
    multi_article_ok = None
    if len(case.expected_targets) > 1:
        multi_article_ok = selected_coverage_ok and citation_ok

    forbidden_primary_targets = (
        *case.forbidden_primary_targets,
        *(target for target in case.expected_targets if target.forbidden_primary),
    )
    forbidden_citation_targets = (
        *case.forbidden_citation_targets,
        *(target for target in case.expected_targets if target.forbidden_citation),
    )
    forbidden_selected = [
        item
        for item in selected_summaries[:1]
        if any(_summary_matches_target(item, target) for target in forbidden_primary_targets)
    ]
    forbidden_cited = [
        item
        for item in prompt_summaries
        if any(_summary_matches_target(item, target) for target in forbidden_citation_targets)
    ]
    forbidden_selected.extend(
        [
            item
            for item in selected_summaries
            if case.forbid_labor_termination_articles
            and _is_labor_termination_article(item.get("law_id"), item.get("article_number"))
        ]
    )
    forbidden_cited.extend(
        [
            item
            for item in prompt_summaries
            if case.forbid_labor_termination_articles
            and _is_labor_termination_article(item.get("law_id"), item.get("article_number"))
        ]
    )
    forbidden_selected = _deduplicate_summaries(forbidden_selected)
    forbidden_cited = _deduplicate_summaries(forbidden_cited)
    pass_reasons = []
    if any(rank is None for rank in candidate_ranks.values()):
        pass_reasons.append("expected candidate missing")
    if not selected_coverage_ok:
        pass_reasons.append("expected target missing from selected evidence")
    if not primary_ok:
        pass_reasons.append("primary evidence mismatch")
    if not citation_ok:
        pass_reasons.append("citation alignment mismatch")
    if forbidden_selected or forbidden_cited:
        pass_reasons.append("forbidden labor termination evidence found")

    primary_packet = selection.selected_evidence[0].packet if selection.selected_evidence else None
    return CaseEvaluation(
        case_id=case.case_id,
        query=case.query,
        split=case.split,
        intent=case.intent,
        expected_targets=case.expected_targets,
        primary_target=case.primary_target,
        candidate_ranks=candidate_ranks,
        selection_input_ranks=selection_input_ranks,
        selection_input_top_k=runtime_config.selection_input_top_k,
        selected_evidence=selected_summaries,
        prompt_evidence=prompt_summaries,
        forbidden_selected=forbidden_selected,
        forbidden_cited=forbidden_cited,
        pass_status=not pass_reasons,
        pass_reason="pass" if not pass_reasons else "; ".join(pass_reasons),
        primary_evidence_accuracy=primary_ok,
        citation_alignment_accuracy=citation_ok,
        multi_article_coverage_accuracy=multi_article_ok,
        cross_reference_only_primary_error=_is_reference_only_primary_error(primary_packet, case),
        wrong_actor_primary_error=(
            "wrong_actor_sensitive" in case.error_categories and not primary_ok
        ),
        wrong_domain_primary_error=(
            case.primary_target is not None
            and primary_packet is not None
            and getattr(primary_packet, "law_id", None) != case.primary_target.law_id
        ),
    )


def _install_target_repo(repo_root: Path) -> None:
    repo_root = repo_root.resolve()
    for name in list(sys.modules):
        if name == "src" or name.startswith("src.retrieval") or name.startswith("src.indexing"):
            del sys.modules[name]
    sys.path.insert(0, str(repo_root))
    importlib.invalidate_caches()


def _load_target_pipeline_modules() -> dict[str, Any]:
    evidence = importlib.import_module("src.retrieval.evidence")
    prompting = importlib.import_module("src.retrieval.prompting")
    selection = importlib.import_module("src.retrieval.selection")
    sparse = importlib.import_module("src.retrieval.sparse_retriever")
    return {
        "ContextAssemblyConfig": evidence.ContextAssemblyConfig,
        "build_evidence_bundle": evidence.build_evidence_bundle,
        "build_naive_rag_prompt": prompting.build_naive_rag_prompt,
        "EvidenceSelectionConfig": selection.EvidenceSelectionConfig,
        "select_evidence_for_answer": selection.select_evidence_for_answer,
        "SparseBM25Retriever": sparse.SparseBM25Retriever,
    }


def _selection_input_retrieval(retrieval: Any, *, selection_input_top_k: int) -> Any:
    """Return a retrieval result view bounded to the runtime selection input."""
    bounded_results = list(retrieval.results[:selection_input_top_k])
    metadata = dict(getattr(retrieval, "metadata", {}) or {})
    metadata["diagnostic_result_count"] = len(retrieval.results)
    metadata["selection_input_top_k"] = selection_input_top_k
    return retrieval.model_copy(
        update={
            "top_k": selection_input_top_k,
            "results": bounded_results,
            "metadata": metadata,
        }
    )


def _git_revision(repo_root: Path) -> str | None:
    """Return the evaluated checkout revision without failing benchmark execution."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def _provision_summary(item: Any, rank: int) -> dict[str, Any]:
    text = getattr(getattr(item, "safe_citable_text", None), "text", None) or getattr(
        item,
        "citable_text",
        None,
    )
    return {
        "rank": rank,
        "packet_id": getattr(item, "packet_id", None),
        "chunk_id": getattr(item, "chunk_id", None),
        "law_id": getattr(item, "law_id", None),
        "article_number": getattr(item, "article_number", None),
        "clause_number": getattr(item, "clause_number", None),
        "point_label": getattr(item, "point_label", None),
        "citation": getattr(item, "citation", None),
        "score": getattr(item, "score", None),
        "role": "primary" if rank == 1 else "supporting",
        "reference_only": bool(text and REFERENCE_ONLY_PATTERN.search(text)),
    }


def parse_evidence_target(raw: str) -> EvidenceTarget:
    """Parse ``law_id:article[:clause[:point]]`` into an evidence target."""
    parts = [part.strip() for part in raw.split(":")]
    if len(parts) < 2 or len(parts) > 4 or not all(parts[:2]):
        raise ValueError("expected target format is law_id:article[:clause[:point]]")
    return EvidenceTarget(
        law_id=parts[0],
        article_number=parts[1],
        clause_number=parts[2] if len(parts) >= 3 and parts[2] else None,
        point_label=parts[3] if len(parts) >= 4 and parts[3] else None,
    )


def evidence_target_from_mapping(raw: dict[str, Any]) -> EvidenceTarget:
    """Build an evidence target from a JSON-compatible mapping."""
    alternatives = tuple(
        evidence_target_from_mapping(item) for item in raw.get("acceptable_alternatives", [])
    )
    return EvidenceTarget(
        law_id=str(raw["law_id"]),
        article_number=str(raw["article_number"]),
        clause_number=str(raw["clause_number"]) if raw.get("clause_number") else None,
        point_label=str(raw["point_label"]) if raw.get("point_label") else None,
        role=str(raw.get("role") or "required"),
        acceptable_alternatives=alternatives,
        forbidden_primary=bool(raw.get("forbidden_primary", False)),
        forbidden_citation=bool(raw.get("forbidden_citation", False)),
    )


def provision_summary(item: Any, *, rank: int) -> dict[str, Any]:
    """Return the canonical law/article/clause/point summary for one provision."""
    return _provision_summary(item, rank)


def target_rank(candidates: Iterable[Any], target: EvidenceTarget) -> int | None:
    """Return the first candidate rank matching the expected target."""
    return _target_rank(candidates, target)


def object_matches_target(item: Any, target: EvidenceTarget) -> bool:
    """Return whether an object with legal locator attributes matches a target."""
    return _object_matches_target(item, target)


def summary_matches_target(item: dict[str, Any], target: EvidenceTarget) -> bool:
    """Return whether a JSON provision summary matches a target."""
    return _summary_matches_target(item, target)


def target_key(target: EvidenceTarget) -> str:
    """Return the canonical target key used in per-case report rows."""
    return target.as_key()


def _target_rank(candidates: Iterable[Any], target: EvidenceTarget) -> int | None:
    for candidate in candidates:
        if _object_matches_target(candidate, target):
            return candidate.rank
    return None


def _object_matches_target(item: Any, target: EvidenceTarget) -> bool:
    return (
        getattr(item, "law_id", None) == target.law_id
        and getattr(item, "article_number", None) == target.article_number
        and (
            target.clause_number is None
            or getattr(item, "clause_number", None) == target.clause_number
        )
        and (target.point_label is None or getattr(item, "point_label", None) == target.point_label)
    )


def _summary_matches_target(item: dict[str, Any], target: EvidenceTarget) -> bool:
    return (
        item.get("law_id") == target.law_id
        and item.get("article_number") == target.article_number
        and (target.clause_number is None or item.get("clause_number") == target.clause_number)
        and (target.point_label is None or item.get("point_label") == target.point_label)
    )


def _is_labor_termination_article(law_id: str | None, article_number: str | None) -> bool:
    return law_id == LABOR_LAW_ID and article_number in {"35", "36", "39"}


def _is_reference_only_primary_error(primary_packet: Any | None, case: BenchmarkCase) -> bool:
    if primary_packet is None:
        return False
    text = getattr(getattr(primary_packet, "safe_citable_text", None), "text", None)
    if not text or not REFERENCE_ONLY_PATTERN.search(text):
        return False
    if case.primary_target is not None and _object_matches_target(
        primary_packet, case.primary_target
    ):
        return False
    return True


def _split_counts(cases: Sequence[BenchmarkCase]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.split] = counts.get(case.split, 0) + 1
    return counts


def _deduplicate_summaries(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    unique: list[dict[str, Any]] = []
    for item in items:
        key = (
            item.get("chunk_id"),
            item.get("law_id"),
            item.get("article_number"),
            item.get("clause_number"),
            item.get("point_label"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _target_granularity(target: EvidenceTarget) -> str:
    if target.point_label is not None:
        return "law_article_clause_point"
    if target.clause_number is not None:
        return "law_article_clause"
    return "law_article"


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _case_rate(cases: Sequence[dict[str, Any]], key: str) -> float:
    return _safe_div(sum(1 for case in cases if case[key]), len(cases))


def _case_regressions(
    before_case: dict[str, Any],
    after_case: dict[str, Any],
) -> list[dict[str, Any]]:
    regressions: list[dict[str, Any]] = []
    boolean_fields = (
        "primary_evidence_accuracy",
        "citation_alignment_accuracy",
        "multi_article_coverage_accuracy",
        "pass",
    )
    for field_name in boolean_fields:
        if before_case.get(field_name) is True and after_case.get(field_name) is not True:
            regressions.append(
                {
                    "case_id": after_case["case_id"],
                    "type": field_name,
                    "before": before_case.get(field_name),
                    "after": after_case.get(field_name),
                }
            )

    before_targets = {target["target_key"]: target for target in before_case["expected_targets"]}
    for after_target in after_case["expected_targets"]:
        before_target = before_targets[after_target["target_key"]]
        before_rank = before_target["candidate_rank"]
        after_rank = after_target["candidate_rank"]
        if before_rank is None:
            continue
        if after_rank is None or after_rank > before_rank:
            regressions.append(
                {
                    "case_id": after_case["case_id"],
                    "type": "candidate_rank_loss",
                    "target_key": after_target["target_key"],
                    "before_rank": before_rank,
                    "after_rank": after_rank,
                    "case_still_passing": bool(after_case["pass"]),
                }
            )
    return regressions


def _case_improved(before_case: dict[str, Any], after_case: dict[str, Any]) -> bool:
    if before_case["pass"] is False and after_case["pass"] is True:
        return True
    before_ranks = [
        target["candidate_rank"]
        for target in before_case["expected_targets"]
        if target["candidate_rank"] is not None
    ]
    after_ranks = [
        target["candidate_rank"]
        for target in after_case["expected_targets"]
        if target["candidate_rank"] is not None
    ]
    return bool(before_ranks and after_ranks and min(after_ranks) < min(before_ranks))


def _target_ranks(cases: Sequence[dict[str, Any]]) -> dict[tuple[str, str], int | None]:
    return {
        (case["case_id"], target["target_key"]): target["candidate_rank"]
        for case in cases
        for target in case["expected_targets"]
    }


def write_json_report(report: dict[str, Any], output_path: Path) -> None:
    """Write a machine-readable report outside protected data by caller choice."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_json_report(path: Path) -> dict[str, Any]:
    """Load one benchmark report from disk."""
    return json.loads(path.read_text(encoding="utf-8"))
