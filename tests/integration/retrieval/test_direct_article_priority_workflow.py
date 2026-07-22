"""Golden retrieval/evidence tests for direct legal article priority."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from src.retrieval.evidence import ContextAssemblyConfig, build_evidence_bundle
from src.retrieval.prompting import build_naive_rag_prompt
from src.retrieval.selection import select_evidence_for_answer
from src.retrieval.sparse_retriever import SparseBM25Retriever

CHUNKS_PATH = Path("data/processed/legal_chunks.jsonl")
LABOR_LAW_ID = "BLLD_VBHN"
BENCHMARK_CONTEXT_CONFIG = ContextAssemblyConfig(max_packets=50)
RUNTIME_ALIGNED_CONTEXT_CONFIG = ContextAssemblyConfig(max_packets=10)


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    query: str
    expected_article: str
    expected_primary_clauses: tuple[str | None, ...]


@dataclass(frozen=True)
class ExpectedEvidenceTarget:
    law_id: str
    article_number: str
    clause_number: str | None = None
    point_label: str | None = None


@dataclass(frozen=True)
class HoldoutCase:
    case_id: str
    query: str
    intent: str
    expected_targets: tuple[ExpectedEvidenceTarget, ...]
    primary_target: ExpectedEvidenceTarget | None = None
    forbid_labor_termination_articles: bool = False


GOLDEN_CASES = (
    GoldenCase(
        case_id="employee_unilateral_termination",
        query="Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        expected_article="35",
        expected_primary_clauses=("1", "2"),
    ),
    GoldenCase(
        case_id="employer_unilateral_termination",
        query="Người sử dụng lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        expected_article="36",
        expected_primary_clauses=("1",),
    ),
    GoldenCase(
        case_id="unlawful_unilateral_termination",
        query="Khi nào đơn phương chấm dứt hợp đồng lao động bị coi là trái pháp luật?",
        expected_article="39",
        expected_primary_clauses=(None,),
    ),
    GoldenCase(
        case_id="employee_notice_period",
        query="Người lao động phải báo trước bao lâu khi đơn phương chấm dứt hợp đồng?",
        expected_article="35",
        expected_primary_clauses=("1",),
    ),
    GoldenCase(
        case_id="employee_no_notice",
        query="Người lao động có được nghỉ việc không cần báo trước trong trường hợp nào?",
        expected_article="35",
        expected_primary_clauses=("2",),
    ),
)

ARTICLE_35_RUNTIME_CUTOFF_CASES = (
    (
        "employee_unilateral_termination",
        "Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?",
        ExpectedEvidenceTarget(LABOR_LAW_ID, "35"),
        {7},
    ),
    (
        "employee_notice_period",
        "Người lao động phải báo trước bao lâu khi đơn phương chấm dứt hợp đồng?",
        ExpectedEvidenceTarget(LABOR_LAW_ID, "35", "1"),
        {4},
    ),
    (
        "employee_no_notice",
        "Người lao động có được nghỉ việc không cần báo trước trong trường hợp nào?",
        ExpectedEvidenceTarget(LABOR_LAW_ID, "35", "2"),
        {6},
    ),
)

OUT_OF_TOPIC_HOLDOUT_CASES = (
    HoldoutCase(
        case_id="worker_maternity_return_notice",
        query=(
            "Khoản 4 Điều 139 Bộ luật Lao động quy định lao động nữ đi làm trước "
            "khi hết thời gian nghỉ thai sản phải báo trước thế nào?"
        ),
        intent="maternity_leave_notice",
        expected_targets=(ExpectedEvidenceTarget(LABOR_LAW_ID, "139", "4"),),
        primary_target=ExpectedEvidenceTarget(LABOR_LAW_ID, "139", "4"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="worker_weekly_rest",
        query=(
            "Khoản 1 Điều 111 Bộ luật Lao động quy định người lao động được nghỉ "
            "hằng tuần ít nhất bao lâu?"
        ),
        intent="weekly_rest",
        expected_targets=(ExpectedEvidenceTarget(LABOR_LAW_ID, "111", "1"),),
        primary_target=ExpectedEvidenceTarget(LABOR_LAW_ID, "111", "1"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="worker_annual_leave",
        query="Khoản 1 Điều 113 Bộ luật Lao động quy định người lao động nghỉ hằng năm bao nhiêu ngày?",
        intent="annual_leave",
        expected_targets=(ExpectedEvidenceTarget(LABOR_LAW_ID, "113", "1"),),
        primary_target=ExpectedEvidenceTarget(LABOR_LAW_ID, "113", "1"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="civil_unlawful_transaction",
        query=(
            "Giao dịch dân sự trái pháp luật do vi phạm điều cấm của luật hoặc "
            "trái đạo đức xã hội theo Điều 123 Bộ luật Dân sự thế nào?"
        ),
        intent="civil_transaction_validity",
        expected_targets=(ExpectedEvidenceTarget("BLDS_2015", "123"),),
        primary_target=ExpectedEvidenceTarget("BLDS_2015", "123"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="civil_authorization_unilateral_termination",
        query=(
            "Khoản 1 Điều 569 Bộ luật Dân sự quy định bên ủy quyền đơn phương "
            "chấm dứt hợp đồng ủy quyền thế nào?"
        ),
        intent="civil_authorization_contract",
        expected_targets=(ExpectedEvidenceTarget("BLDS_2015", "569", "1"),),
        primary_target=ExpectedEvidenceTarget("BLDS_2015", "569", "1"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="marriage_age_condition",
        query=(
            "Điểm a khoản 1 Điều 8 Luật Hôn nhân và gia đình quy định điều kiện "
            "kết hôn về độ tuổi thế nào?"
        ),
        intent="marriage_conditions",
        expected_targets=(ExpectedEvidenceTarget("LHNGD_VBHN", "8", "1", "a"),),
        primary_target=ExpectedEvidenceTarget("LHNGD_VBHN", "8", "1", "a"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="land_user_common_rights",
        query="Khoản 1 Điều 26 Luật Đất đai quy định quyền chung của người sử dụng đất thế nào?",
        intent="land_user_rights",
        expected_targets=(ExpectedEvidenceTarget("LDD_VBHN", "26", "1"),),
        primary_target=ExpectedEvidenceTarget("LDD_VBHN", "26", "1"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="health_insurance_information_duty",
        query=(
            "Khoản 4 Điều 39 Luật Bảo hiểm y tế quy định trách nhiệm cung cấp thông tin thế nào?"
        ),
        intent="health_insurance_duties",
        expected_targets=(ExpectedEvidenceTarget("LBHYT_VBHN", "39", "4"),),
        primary_target=ExpectedEvidenceTarget("LBHYT_VBHN", "39", "4"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="notary_reporting_duty",
        query=(
            "Khoản 8 Điều 36 Luật Công chứng quy định nghĩa vụ báo cáo, kiểm tra, "
            "thanh tra thế nào?"
        ),
        intent="notary_organization_duties",
        expected_targets=(ExpectedEvidenceTarget("LCCONGCHUNG_VBHN", "36", "8"),),
        primary_target=ExpectedEvidenceTarget("LCCONGCHUNG_VBHN", "36", "8"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="notary_cross_reference_direct_target",
        query=(
            "Khoản 5 Điều 36 Luật Công chứng quy định nghĩa vụ mua bảo hiểm "
            "trách nhiệm nghề nghiệp của tổ chức hành nghề công chứng thế nào?"
        ),
        intent="direct_cross_reference_target",
        expected_targets=(ExpectedEvidenceTarget("LCCONGCHUNG_VBHN", "36", "5"),),
        primary_target=ExpectedEvidenceTarget("LCCONGCHUNG_VBHN", "36", "5"),
        forbid_labor_termination_articles=True,
    ),
    HoldoutCase(
        case_id="weekly_and_annual_leave_multi_article",
        query=(
            "Khoản 1 Điều 111 và Khoản 1 Điều 113 Bộ luật Lao động quy định nghỉ "
            "hằng tuần và nghỉ hằng năm thế nào?"
        ),
        intent="multi_article_leave_coverage",
        expected_targets=(
            ExpectedEvidenceTarget(LABOR_LAW_ID, "111", "1"),
            ExpectedEvidenceTarget(LABOR_LAW_ID, "113", "1"),
        ),
        primary_target=ExpectedEvidenceTarget(LABOR_LAW_ID, "111", "1"),
        forbid_labor_termination_articles=True,
    ),
)

BROAD_CROSS_DOMAIN_CASES = (
    HoldoutCase(
        case_id="constitutional_human_rights",
        query="Khoản 1 Điều 14 Hiến pháp quy định quyền con người, quyền công dân thế nào?",
        intent="constitutional_rights",
        expected_targets=(ExpectedEvidenceTarget("HP_2013", "14", "1"),),
        primary_target=ExpectedEvidenceTarget("HP_2013", "14", "1"),
    ),
    HoldoutCase(
        case_id="criminal_code_crime_definition",
        query="Khoản 1 Điều 8 Bộ luật Hình sự quy định khái niệm tội phạm thế nào?",
        intent="criminal_definition",
        expected_targets=(ExpectedEvidenceTarget("BLHS_VBHN", "8", "1"),),
        primary_target=ExpectedEvidenceTarget("BLHS_VBHN", "8", "1"),
    ),
    HoldoutCase(
        case_id="civil_procedure_litigant_duty",
        query="Khoản 1 Điều 70 Bộ luật Tố tụng dân sự quy định nghĩa vụ của đương sự thế nào?",
        intent="civil_procedure_actor_duty",
        expected_targets=(ExpectedEvidenceTarget("BLTTDS_VBHN", "70", "1"),),
        primary_target=ExpectedEvidenceTarget("BLTTDS_VBHN", "70", "1"),
    ),
    HoldoutCase(
        case_id="criminal_procedure_accused_definition",
        query="Khoản 1 Điều 60 Bộ luật Tố tụng hình sự quy định bị can là ai?",
        intent="criminal_procedure_actor_definition",
        expected_targets=(ExpectedEvidenceTarget("BLTTHS_VBHN", "60", "1"),),
        primary_target=ExpectedEvidenceTarget("BLTTHS_VBHN", "60", "1"),
    ),
    HoldoutCase(
        case_id="food_safety_prohibited_act",
        query="Khoản 1 Điều 5 Luật An toàn thực phẩm quy định hành vi bị cấm nào?",
        intent="prohibition",
        expected_targets=(ExpectedEvidenceTarget("LATTP_VBHN", "5", "1"),),
        primary_target=ExpectedEvidenceTarget("LATTP_VBHN", "5", "1"),
    ),
    HoldoutCase(
        case_id="environment_protection_principle",
        query="Khoản 1 Điều 4 Luật Bảo vệ môi trường quy định nguyên tắc bảo vệ môi trường thế nào?",
        intent="environment_principle",
        expected_targets=(ExpectedEvidenceTarget("LBVMT_VBHN", "4", "1"),),
        primary_target=ExpectedEvidenceTarget("LBVMT_VBHN", "4", "1"),
    ),
    HoldoutCase(
        case_id="enterprise_business_right",
        query="Khoản 1 Điều 7 Luật Doanh nghiệp quy định quyền tự do kinh doanh thế nào?",
        intent="enterprise_permission",
        expected_targets=(ExpectedEvidenceTarget("LDN_VBHN", "7", "1"),),
        primary_target=ExpectedEvidenceTarget("LDN_VBHN", "7", "1"),
    ),
    HoldoutCase(
        case_id="commerce_sale_contract_form",
        query="Khoản 1 Điều 24 Luật Thương mại quy định hình thức hợp đồng mua bán hàng hóa thế nào?",
        intent="commerce_contract_form",
        expected_targets=(ExpectedEvidenceTarget("LTM_VBHN", "24", "1"),),
        primary_target=ExpectedEvidenceTarget("LTM_VBHN", "24", "1"),
    ),
    HoldoutCase(
        case_id="ip_right_definition",
        query="Khoản 1 Điều 4 Luật Sở hữu trí tuệ giải thích quyền sở hữu trí tuệ là gì?",
        intent="intellectual_property_definition",
        expected_targets=(ExpectedEvidenceTarget("LSHTT_VBHN", "4", "1"),),
        primary_target=ExpectedEvidenceTarget("LSHTT_VBHN", "4", "1"),
    ),
    HoldoutCase(
        case_id="housing_owner_right_point",
        query="Điểm a khoản 1 Điều 10 Luật Nhà ở quy định quyền bất khả xâm phạm về nhà ở thế nào?",
        intent="housing_owner_right",
        expected_targets=(ExpectedEvidenceTarget("LNO_VBHN", "10", "1", "a"),),
        primary_target=ExpectedEvidenceTarget("LNO_VBHN", "10", "1", "a"),
    ),
    HoldoutCase(
        case_id="taxpayer_support_right",
        query="Khoản 1 Điều 16 Luật Quản lý thuế quy định quyền được hỗ trợ của người nộp thuế thế nào?",
        intent="taxpayer_right",
        expected_targets=(ExpectedEvidenceTarget("LQLT_VBHN", "16", "1"),),
        primary_target=ExpectedEvidenceTarget("LQLT_VBHN", "16", "1"),
    ),
    HoldoutCase(
        case_id="traffic_general_rule",
        query="Khoản 1 Điều 10 Luật Trật tự, an toàn giao thông đường bộ quy định quy tắc đi bên phải thế nào?",
        intent="traffic_rule",
        expected_targets=(ExpectedEvidenceTarget("LTATGT_VBHN", "10", "1"),),
        primary_target=ExpectedEvidenceTarget("LTATGT_VBHN", "10", "1"),
    ),
    HoldoutCase(
        case_id="employment_state_management_point",
        query="Điểm a khoản 1 Điều 6 Luật Việc làm quy định ban hành văn bản về việc làm thế nào?",
        intent="employment_state_management",
        expected_targets=(ExpectedEvidenceTarget("LVL_2025", "6", "1", "a"),),
        primary_target=ExpectedEvidenceTarget("LVL_2025", "6", "1", "a"),
    ),
    HoldoutCase(
        case_id="citizen_id_card_holder",
        query="Khoản 1 Điều 19 Luật Căn cước quy định người được cấp thẻ căn cước là ai?",
        intent="identity_card_holder",
        expected_targets=(ExpectedEvidenceTarget("LCC_VBHN", "19", "1"),),
        primary_target=ExpectedEvidenceTarget("LCC_VBHN", "19", "1"),
    ),
)


@pytest.fixture(scope="module")
def sparse_retriever() -> SparseBM25Retriever:
    """Build the local sparse retriever once for golden integration checks."""
    if not CHUNKS_PATH.exists():
        pytest.skip(f"processed chunks file is missing: {CHUNKS_PATH}")
    return SparseBM25Retriever.from_jsonl(CHUNKS_PATH, default_top_k=50)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[case.case_id for case in GOLDEN_CASES])
async def test_direct_article_priority_golden_cases(
    sparse_retriever: SparseBM25Retriever,
    case: GoldenCase,
) -> None:
    """Golden questions select and cite the direct substantive article first."""
    retrieval = await sparse_retriever.retrieve(case.query, top_k=50)
    bundle = build_evidence_bundle(retrieval, config=BENCHMARK_CONTEXT_CONFIG)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=case.query, selection_result=selection)

    direct_candidates = [
        chunk
        for chunk in retrieval.results
        if chunk.law_id == LABOR_LAW_ID and chunk.article_number == case.expected_article
    ]
    assert direct_candidates, f"{case.case_id}: expected direct article absent from candidates"

    primary = selection.selected_evidence[0].packet
    primary_citation = prompt.evidence[0]
    assert primary.law_id == LABOR_LAW_ID
    assert primary.article_number == case.expected_article
    assert primary.clause_number in case.expected_primary_clauses
    assert primary_citation.law_id == LABOR_LAW_ID
    assert primary_citation.article_number == case.expected_article
    assert primary_citation.clause_number in case.expected_primary_clauses


@pytest.mark.asyncio
async def test_employee_termination_keeps_article_34_clause_9_auxiliary_not_primary(
    sparse_retriever: SparseBM25Retriever,
) -> None:
    """Article 34 Clause 9 may appear as a cross-reference, but is not primary."""
    query = "Người lao động được đơn phương chấm dứt hợp đồng trong trường hợp nào?"
    retrieval = await sparse_retriever.retrieve(query, top_k=50)
    bundle = build_evidence_bundle(retrieval, config=BENCHMARK_CONTEXT_CONFIG)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=query, selection_result=selection)

    article_34_clause_9 = [
        chunk
        for chunk in retrieval.results
        if chunk.law_id == LABOR_LAW_ID
        and chunk.article_number == "34"
        and chunk.clause_number == "9"
    ]
    assert article_34_clause_9
    assert "Điều 35" in (article_34_clause_9[0].text or "")

    primary = selection.selected_evidence[0].packet
    assert primary.article_number == "35"
    assert prompt.evidence[0].article_number == "35"
    assert all(
        not (evidence.article_number == "34" and evidence.clause_number == "9")
        for evidence in prompt.evidence
    )
    assert all(
        selected.packet.article_number != "39" for selected in selection.selected_evidence[:1]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case_id", "query", "target", "accepted_sparse_ranks"),
    ARTICLE_35_RUNTIME_CUTOFF_CASES,
    ids=[case[0] for case in ARTICLE_35_RUNTIME_CUTOFF_CASES],
)
async def test_article_35_rank_regressions_survive_runtime_aligned_sparse_cutoff(
    sparse_retriever: SparseBM25Retriever,
    case_id: str,
    query: str,
    target: ExpectedEvidenceTarget,
    accepted_sparse_ranks: set[int],
) -> None:
    """Article 35 targets remain primary/cited from top-10 sparse selection input."""
    retrieval = await sparse_retriever.retrieve(query, top_k=50)
    selection_retrieval = retrieval.model_copy(
        update={"top_k": 10, "results": retrieval.results[:10]}
    )
    bundle = build_evidence_bundle(selection_retrieval, config=RUNTIME_ALIGNED_CONTEXT_CONFIG)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=query, selection_result=selection)
    diagnostics = _runtime_cutoff_diagnostics(
        case_id,
        retrieval.results,
        selection.selected_evidence,
        prompt.evidence,
        target,
    )

    sparse_rank = _target_rank(retrieval.results, target)
    assert sparse_rank in accepted_sparse_ranks, diagnostics
    assert sparse_rank is not None and sparse_rank <= 10, diagnostics
    assert _packet_matches_target(selection.selected_evidence[0].packet, target), diagnostics
    assert _prompt_evidence_matches_target(prompt.evidence[0], target), diagnostics
    assert all(
        not (
            selected.packet.law_id == LABOR_LAW_ID
            and selected.packet.article_number in {"34", "36", "39"}
        )
        for selected in selection.selected_evidence[:1]
    ), diagnostics


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    OUT_OF_TOPIC_HOLDOUT_CASES,
    ids=[case.case_id for case in OUT_OF_TOPIC_HOLDOUT_CASES],
)
async def test_out_of_topic_holdout_cases_retain_expected_evidence_and_citations(
    sparse_retriever: SparseBM25Retriever,
    case: HoldoutCase,
) -> None:
    """Termination-specific heuristics must not displace other legal intents."""
    retrieval = await sparse_retriever.retrieve(case.query, top_k=50)
    bundle = build_evidence_bundle(retrieval, config=BENCHMARK_CONTEXT_CONFIG)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=case.query, selection_result=selection)
    diagnostics = _case_diagnostics(
        case, retrieval.results, selection.selected_evidence, prompt.evidence
    )

    for target in case.expected_targets:
        assert _target_rank(retrieval.results, target) is not None, diagnostics
        assert _target_present_in_selected(selection.selected_evidence, target), diagnostics
        assert _target_present_in_prompt(prompt.evidence, target), diagnostics

    if case.primary_target is not None:
        assert _packet_matches_target(selection.selected_evidence[0].packet, case.primary_target), (
            diagnostics
        )
        assert _prompt_evidence_matches_target(prompt.evidence[0], case.primary_target), diagnostics

    if case.forbid_labor_termination_articles:
        selected_forbidden = [
            selected.packet
            for selected in selection.selected_evidence
            if _is_labor_termination_article(
                selected.packet.law_id,
                selected.packet.article_number,
            )
        ]
        prompt_forbidden = [
            evidence
            for evidence in prompt.evidence
            if _is_labor_termination_article(evidence.law_id, evidence.article_number)
        ]
        assert not selected_forbidden, diagnostics
        assert not prompt_forbidden, diagnostics


@pytest.mark.asyncio
async def test_direct_cross_reference_target_is_not_dropped(
    sparse_retriever: SparseBM25Retriever,
) -> None:
    """A cross-reference provision remains citable when it is the direct target."""
    case = next(
        item
        for item in OUT_OF_TOPIC_HOLDOUT_CASES
        if item.case_id == "notary_cross_reference_direct_target"
    )
    target = case.expected_targets[0]
    retrieval = await sparse_retriever.retrieve(case.query, top_k=50)
    bundle = build_evidence_bundle(retrieval, config=BENCHMARK_CONTEXT_CONFIG)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=case.query, selection_result=selection)
    diagnostics = _case_diagnostics(
        case, retrieval.results, selection.selected_evidence, prompt.evidence
    )

    target_candidate = next(
        chunk for chunk in retrieval.results if _chunk_matches_target(chunk, target)
    )

    assert "theo quy định tại Điều 39" in (target_candidate.text or "")
    assert _target_present_in_selected(selection.selected_evidence, target), diagnostics
    assert _target_present_in_prompt(prompt.evidence, target), diagnostics


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    BROAD_CROSS_DOMAIN_CASES,
    ids=[case.case_id for case in BROAD_CROSS_DOMAIN_CASES],
)
async def test_broad_cross_domain_cases_select_primary_evidence(
    sparse_retriever: SparseBM25Retriever,
    case: HoldoutCase,
) -> None:
    """Broad cross-domain cases require the direct provision as primary evidence."""
    retrieval = await sparse_retriever.retrieve(case.query, top_k=50)
    bundle = build_evidence_bundle(retrieval, config=BENCHMARK_CONTEXT_CONFIG)
    selection = select_evidence_for_answer(bundle)
    prompt = build_naive_rag_prompt(query=case.query, selection_result=selection)
    diagnostics = _case_diagnostics(
        case, retrieval.results, selection.selected_evidence, prompt.evidence
    )

    assert case.primary_target is not None
    assert _packet_matches_target(selection.selected_evidence[0].packet, case.primary_target), (
        diagnostics
    )
    assert _prompt_evidence_matches_target(prompt.evidence[0], case.primary_target), diagnostics
    for target in case.expected_targets:
        assert _target_rank(retrieval.results, target) is not None, diagnostics
        assert _target_present_in_selected(selection.selected_evidence, target), diagnostics
        assert _target_present_in_prompt(prompt.evidence, target), diagnostics


def _case_diagnostics(
    case: HoldoutCase,
    candidates: list[object],
    selected: list[object],
    prompt_evidence: list[object],
) -> str:
    expected = [
        {
            "law_id": target.law_id,
            "article_number": target.article_number,
            "clause_number": target.clause_number,
            "point_label": target.point_label,
            "candidate_rank": _target_rank(candidates, target),
        }
        for target in case.expected_targets
    ]
    return (
        f"case={case.case_id} intent={case.intent} expected={expected} "
        f"selected={[_selected_summary(item) for item in selected]} "
        f"citations={[_prompt_summary(item) for item in prompt_evidence]}"
    )


def _runtime_cutoff_diagnostics(
    case_id: str,
    candidates: list[object],
    selected: list[object],
    prompt_evidence: list[object],
    target: ExpectedEvidenceTarget,
) -> str:
    return (
        f"case={case_id} expected={target} target_rank={_target_rank(candidates, target)} "
        f"top10={[_candidate_summary(item) for item in candidates[:10]]} "
        f"selected={[_selected_summary(item) for item in selected]} "
        f"citations={[_prompt_summary(item) for item in prompt_evidence]}"
    )


def _target_rank(candidates: list[object], target: ExpectedEvidenceTarget) -> int | None:
    for candidate in candidates:
        if _chunk_matches_target(candidate, target):
            return candidate.rank
    return None


def _target_present_in_selected(
    selected: list[object],
    target: ExpectedEvidenceTarget,
) -> bool:
    return any(_packet_matches_target(item.packet, target) for item in selected)


def _target_present_in_prompt(
    prompt_evidence: list[object],
    target: ExpectedEvidenceTarget,
) -> bool:
    return any(_prompt_evidence_matches_target(item, target) for item in prompt_evidence)


def _chunk_matches_target(chunk: object, target: ExpectedEvidenceTarget) -> bool:
    return (
        chunk.law_id == target.law_id
        and chunk.article_number == target.article_number
        and (target.clause_number is None or chunk.clause_number == target.clause_number)
        and (target.point_label is None or chunk.point_label == target.point_label)
    )


def _packet_matches_target(packet: object, target: ExpectedEvidenceTarget) -> bool:
    return (
        packet.law_id == target.law_id
        and packet.article_number == target.article_number
        and (target.clause_number is None or packet.clause_number == target.clause_number)
        and (target.point_label is None or packet.point_label == target.point_label)
    )


def _prompt_evidence_matches_target(item: object, target: ExpectedEvidenceTarget) -> bool:
    return (
        item.law_id == target.law_id
        and item.article_number == target.article_number
        and (target.clause_number is None or item.clause_number == target.clause_number)
        and (target.point_label is None or item.point_label == target.point_label)
    )


def _is_labor_termination_article(law_id: str | None, article_number: str | None) -> bool:
    return law_id == LABOR_LAW_ID and article_number in {"35", "36", "39"}


def _selected_summary(item: object) -> tuple[str | None, str | None, str | None, str | None]:
    packet = item.packet
    return (packet.law_id, packet.article_number, packet.clause_number, packet.point_label)


def _prompt_summary(item: object) -> tuple[str | None, str | None, str | None, str | None]:
    return (item.law_id, item.article_number, item.clause_number, item.point_label)


def _candidate_summary(item: object) -> tuple[int, str | None, str | None, str | None, str | None]:
    return (
        item.rank,
        item.law_id,
        item.article_number,
        item.clause_number,
        item.point_label,
    )
