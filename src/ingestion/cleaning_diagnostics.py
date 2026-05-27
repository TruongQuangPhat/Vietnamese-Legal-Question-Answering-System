"""Reusable diagnostic logic for cleaning quality audits.

This module computes diagnostics for raw HTML, selector candidates,
current normalized outputs, raw-vs-cleaning comparisons, and coarse law pattern
groups. It does not mutate raw artifacts or invoke the cleaning pipeline.
"""

from __future__ import annotations

import datetime
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup

from src.ingestion.audit import scan_raw_artifacts


ARTICLE_REFERENCE_RE = re.compile(r"\bĐiều\s+(\d+)\b", re.IGNORECASE)
ARTICLE_HEADING_RE = re.compile(r"(?m)^\s*Điều\s+(\d+)\s*[\.:]?", re.IGNORECASE)
CLAUSE_HEADING_RE = re.compile(r"(?m)^\s*\d+\.")
POINT_HEADING_RE = re.compile(r"(?m)^\s*[a-zđ]\)", re.IGNORECASE)
BROKEN_ARTICLE_HEADING_RE = re.compile(r"(?m)^\s*Đ\s*i\s*ề\s*u(?:\s*$|\s+[^\d])", re.IGNORECASE)
SPLIT_VIETNAMESE_WORD_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bĐ\s+iều\b",
        r"\bCh\s+ương\b",
        r"\bKho\s+ản\b",
        r"\bĐi\s+ểm\b",
        r"\bM\s+ục\b",
        r"\bPh\s+ần\b",
        r"\bLu\s+ật\b",
        r"\bQu\s+ốc\s+hội\b",
    )
)
END_NOISE_MARKERS = (
    "Văn bản liên quan",
    "Liên quan hiệu lực",
    "Liên quan nội dung",
    "Thuộc tính",
    "Bình luận",
    "Hỏi đáp",
)
START_NOISE_MARKERS = (
    "THƯ VIỆN PHÁP LUẬT",
    "Đăng nhập",
    "Đăng ký",
    "Tra cứu",
    "Tìm kiếm",
)
SELECTOR_CANDIDATES = ("#divContentDoc", "#divContentDoc .content1", ".content1", "body")
PATTERN_GROUP_NAMES = (
    "Constitution",
    "Original large code",
    "Consolidated large codes",
    "Original ordinary laws",
    "Consolidated ordinary laws",
    "Government/judiciary organization laws",
    "Other",
)


def ping_diagnostics() -> str:
    """Check that the diagnostics module is importable."""
    return "cleaning_diagnostics_ok"


@dataclass
class CorpusInventory:
    """Inventory counts for the legal corpus at different stages."""

    registry_entries: int = 0
    main_html_files: int = 0
    metadata_json_files: int = 0
    normalized_json_files: int = 0
    cleaned_txt_files: int = 0
    report_files: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert the inventory to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class HTMLPatternProfile:
    """Profile of HTML structure patterns for a raw legal document."""

    law_id: str
    raw_html_size_bytes: int
    has_divContentDoc: bool
    divContentDoc_count: int
    content1_global_count: int
    divContentDoc_content1_count: int
    raw_dieu_count: int
    has_dieu_1: bool
    first_position_of_dieu_1: int | None
    first_position_of_vb_lien_quan: int | None
    first_position_of_thuoc_tinh: int | None

    def to_dict(self) -> dict[str, Any]:
        """Convert the profile to a JSON-serializable dictionary."""
        return asdict(self)


@dataclass
class RawCleanedComparison:
    """Comparison metrics between raw HTML and cleaned output."""

    law_id: str
    raw_html_size_bytes: int
    cleaned_text_chars: int
    raw_marker_counts: dict[str, int]
    cleaned_marker_counts: dict[str, int]
    raw_max_article_reference: int
    cleaned_max_article_heading: int
    raw_has_dieu_1: bool
    cleaned_has_article_1_heading: bool
    compression_ratio: float | None
    possible_missing_body: bool
    possible_over_extraction: bool
    possible_duplicate_extraction: bool
    possible_wrong_start: bool
    possible_wrong_end: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert the comparison to a JSON-serializable dictionary."""
        return asdict(self)


def compute_corpus_inventory(
    registry_path: Path,
    raw_dir: Path,
    interim_dir: Path,
    report_dir: Path,
) -> dict[str, Any]:
    """Count files at each stage of the pipeline.

    Args:
        registry_path: Path to corpus registry YAML.
        raw_dir: Directory containing raw HTML artifacts.
        interim_dir: Directory containing normalized/cleaned artifacts.
        report_dir: Directory containing audit reports.

    Returns:
        Report dictionary with metadata, total_records, items, and errors.
    """
    inventory = CorpusInventory()
    errors: list[dict[str, Any]] = []

    if registry_path.exists():
        try:
            data = _load_registry(registry_path)
            inventory.registry_entries = len(data)
        except Exception as exc:
            errors.append({"stage": "registry", "error": str(exc)})

    if raw_dir.exists():
        try:
            inventory.main_html_files = len(list(raw_dir.rglob("main.html")))
            inventory.metadata_json_files = len(list(raw_dir.rglob("metadata.json")))
        except Exception as exc:
            errors.append({"stage": "raw_dir", "error": str(exc)})

    if interim_dir.exists():
        try:
            inventory.normalized_json_files = len(list(interim_dir.rglob("normalized.json")))
            inventory.cleaned_txt_files = len(list(interim_dir.rglob("cleaned.txt")))
        except Exception as exc:
            errors.append({"stage": "interim_dir", "error": str(exc)})

    if report_dir.exists():
        try:
            inventory.report_files = len([path for path in report_dir.rglob("*") if path.is_file()])
        except Exception as exc:
            errors.append({"stage": "report_dir", "error": str(exc)})

    return _build_report("corpus_inventory", [inventory.to_dict()], errors)


def profile_raw_html(law_id: str, html_path: Path) -> HTMLPatternProfile:
    """Profile raw HTML file for structural markers.

    Args:
        law_id: Law identifier.
        html_path: Path to main.html.

    Returns:
        HTMLPatternProfile with extracted raw HTML metrics.
    """
    content = _read_text(html_path)
    soup = _parse_html(content)
    div_nodes = _select_div_content_doc(soup)
    div_content1_count = sum(len(node.select(".content1")) for node in div_nodes)
    first_dieu_1 = _first_position(content, (r"Điều\s+1\b", r"ĐIỀU\s+1\b", r"điều\s+1\b"))

    return HTMLPatternProfile(
        law_id=law_id,
        raw_html_size_bytes=html_path.stat().st_size,
        has_divContentDoc=bool(div_nodes),
        divContentDoc_count=len(div_nodes),
        content1_global_count=len(soup.select(".content1")),
        divContentDoc_content1_count=div_content1_count,
        raw_dieu_count=len(ARTICLE_REFERENCE_RE.findall(content)),
        has_dieu_1=first_dieu_1 is not None,
        first_position_of_dieu_1=first_dieu_1,
        first_position_of_vb_lien_quan=_find_or_none(content, "Văn bản liên quan"),
        first_position_of_thuoc_tinh=_find_or_none(content, "Thuộc tính"),
    )


def audit_all_raw_html(raw_dir: Path) -> tuple[list[HTMLPatternProfile], list[dict[str, Any]]]:
    """Profile all raw HTML files in the raw directory.

    Args:
        raw_dir: Directory containing raw legal artifacts.

    Returns:
        Tuple of profiles and per-law errors.
    """
    profiles: list[HTMLPatternProfile] = []
    errors: list[dict[str, Any]] = []
    for law_id, artifact_dir in sorted(scan_raw_artifacts(raw_dir).items()):
        try:
            profiles.append(profile_raw_html(law_id, artifact_dir / "main.html"))
        except Exception as exc:
            errors.append({"law_id": law_id, "stage": "html_pattern_audit", "error": str(exc)})
    return profiles, errors


def compute_selector_candidate_audit(raw_dir: Path) -> dict[str, Any]:
    """Audit fixed raw HTML selector candidates for every law.

    Args:
        raw_dir: Directory containing raw legal artifacts.

    Returns:
        Report dictionary with one item per law and selector candidate.
    """
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for law_id, artifact_dir in sorted(scan_raw_artifacts(raw_dir).items()):
        try:
            html = _read_text(artifact_dir / "main.html")
            soup = _parse_html(html)
            for selector in SELECTOR_CANDIDATES:
                records.append(_profile_selector(law_id, soup, selector))
        except Exception as exc:
            errors.append({"law_id": law_id, "stage": "selector_candidate_audit", "error": str(exc)})

    return _build_report("selector_candidate_audit", records, errors)


def compute_cleaning_quality_audit(interim_dir: Path) -> dict[str, Any]:
    """Audit current normalized output quality for each law.

    Args:
        interim_dir: Directory containing normalized.json files.

    Returns:
        Report dictionary with one item per normalized artifact.
    """
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for normalized_path in sorted(interim_dir.rglob("normalized.json")) if interim_dir.exists() else []:
        law_id = normalized_path.parent.name
        try:
            data = _load_json(normalized_path)
            law_id = str(data.get("law_id") or law_id)
            text = str(data.get("normalized_text") or "")
            metrics = _text_quality_metrics(text)
            text_stats = data.get("text_stats") if isinstance(data.get("text_stats"), dict) else {}
            suspicious_flags = _cleaning_suspicious_flags(text, metrics)

            records.append(
                {
                    "law_id": law_id,
                    "normalized_text_chars": int(
                        text_stats.get("normalized_text_chars") or len(text)
                    ),
                    "line_count": int(text_stats.get("line_count") or len(text.splitlines())),
                    "duplicate_line_ratio": metrics["duplicate_line_ratio"],
                    "article_reference_count": metrics["article_reference_count"],
                    "article_heading_count": metrics["article_heading_count"],
                    "max_heading_article_number": metrics["max_heading_article_number"],
                    "has_heading_article_1": metrics["has_heading_article_1"],
                    "heading_sequence_score": metrics["heading_sequence_score"],
                    "broken_article_heading_count": metrics["broken_article_heading_count"],
                    "split_vietnamese_word_count": metrics["split_vietnamese_word_count"],
                    "suspicious_flags": suspicious_flags,
                }
            )
        except Exception as exc:
            errors.append({"law_id": law_id, "stage": "cleaning_quality_audit", "error": str(exc)})

    return _build_report("cleaning_quality_audit", records, errors)


def compute_raw_vs_cleaning_comparison(raw_dir: Path, interim_dir: Path) -> dict[str, Any]:
    """Compare raw HTML markers with current normalized output.

    Args:
        raw_dir: Directory containing raw legal artifacts.
        interim_dir: Directory containing normalized artifacts.

    Returns:
        Report dictionary with one item per comparable law.
    """
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    artifacts = scan_raw_artifacts(raw_dir)

    for law_id, artifact_dir in sorted(artifacts.items()):
        normalized_path = interim_dir / law_id / "normalized.json"
        try:
            if not normalized_path.is_file():
                raise FileNotFoundError(f"normalized artifact not found: {normalized_path}")
            raw_html = _read_text(artifact_dir / "main.html")
            raw_text = _parse_html(raw_html).get_text(separator="\n")
            data = _load_json(normalized_path)
            cleaned_text = str(data.get("normalized_text") or "")
            raw_metrics = _text_quality_metrics(raw_text)
            cleaned_metrics = _text_quality_metrics(cleaned_text)
            raw_size = (artifact_dir / "main.html").stat().st_size
            cleaned_chars = len(cleaned_text)
            compression_ratio = cleaned_chars / raw_size if raw_size else None
            duplicate_line_ratio = cleaned_metrics["duplicate_line_ratio"]

            comparison = RawCleanedComparison(
                law_id=law_id,
                raw_html_size_bytes=raw_size,
                cleaned_text_chars=cleaned_chars,
                raw_marker_counts=_marker_counts(raw_text),
                cleaned_marker_counts=_marker_counts(cleaned_text),
                raw_max_article_reference=raw_metrics["max_article_reference_number"],
                cleaned_max_article_heading=cleaned_metrics["max_heading_article_number"],
                raw_has_dieu_1=raw_metrics["has_reference_article_1"],
                cleaned_has_article_1_heading=cleaned_metrics["has_heading_article_1"],
                compression_ratio=compression_ratio,
                possible_missing_body=_possible_missing_body(raw_metrics, cleaned_metrics, cleaned_chars),
                possible_over_extraction=bool(compression_ratio is not None and compression_ratio > 0.85),
                possible_duplicate_extraction=duplicate_line_ratio > 0.20,
                possible_wrong_start=_has_wrong_start(cleaned_text),
                possible_wrong_end=_has_wrong_end(cleaned_text),
            )
            records.append(comparison.to_dict())
        except Exception as exc:
            errors.append({"law_id": law_id, "stage": "raw_vs_cleaning_comparison", "error": str(exc)})

    return _build_report("raw_vs_cleaning_comparison", records, errors)


def compute_pattern_groups(registry_path: Path, raw_dir: Path, interim_dir: Path) -> dict[str, Any]:
    """Group laws into coarse cleaning pattern categories.

    Args:
        registry_path: Path to the corpus registry.
        raw_dir: Directory containing raw artifacts.
        interim_dir: Directory containing normalized artifacts.

    Returns:
        Report dictionary whose items are pattern groups with law ids.
    """
    errors: list[dict[str, Any]] = []
    registry_entries: list[dict[str, Any]] = []
    raw_artifacts = scan_raw_artifacts(raw_dir)

    try:
        registry_entries = _load_registry(registry_path)
    except Exception as exc:
        errors.append({"stage": "pattern_groups", "error": str(exc)})

    if not registry_entries:
        registry_entries = [{"law_id": law_id, "name": law_id} for law_id in sorted(raw_artifacts)]

    groups: dict[str, list[dict[str, Any]]] = {name: [] for name in PATTERN_GROUP_NAMES}
    for entry in registry_entries:
        law_id = str(entry.get("law_id") or "")
        if not law_id:
            errors.append({"stage": "pattern_groups", "error": "registry entry missing law_id"})
            continue
        try:
            name = str(entry.get("name") or entry.get("law_name") or law_id)
            source_type = str(entry.get("source_type") or "")
            max_article = _normalized_max_article(interim_dir / law_id / "normalized.json")
            group_name = _classify_pattern_group(law_id, name, source_type, max_article)
            groups[group_name].append(
                {
                    "law_id": law_id,
                    "name": name,
                    "source_type": source_type,
                    "max_article_number": max_article,
                }
            )
        except Exception as exc:
            errors.append({"law_id": law_id, "stage": "pattern_groups", "error": str(exc)})

    items = [
        {"group": group_name, "law_count": len(laws), "laws": laws}
        for group_name, laws in groups.items()
    ]
    return _build_report("pattern_groups", items, errors, total_records=sum(len(laws) for laws in groups.values()))


def _build_report(
    audit_type: str,
    items: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    total_records: int | None = None,
) -> dict[str, Any]:
    return {
        "metadata": {
            "audit_type": audit_type,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "audit_version": "1.0",
        },
        "total_records": len(items) if total_records is None else total_records,
        "items": items,
        "errors": errors,
    }


def _load_registry(registry_path: Path) -> list[dict[str, Any]]:
    with registry_path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    corpus = data.get("corpus", [])
    return corpus if isinstance(corpus, list) else []


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object in {path}")
    return data


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        return file.read()


def _parse_html(content: str) -> BeautifulSoup:
    return BeautifulSoup(content, "html.parser")


def _select_div_content_doc(soup: BeautifulSoup) -> list[Any]:
    nodes = list(soup.select("#divContentDoc"))
    seen = {id(node) for node in nodes}
    for node in soup.find_all(attrs={"class": lambda value: value and "divContentDoc" in str(value)}):
        if id(node) not in seen:
            nodes.append(node)
            seen.add(id(node))
    return nodes


def _profile_selector(law_id: str, soup: BeautifulSoup, selector: str) -> dict[str, Any]:
    nodes = soup.select(selector)
    text_by_node = [node.get_text(separator="\n", strip=True) for node in nodes]
    first_text = text_by_node[0] if text_by_node else ""
    all_text = "\n".join(text_by_node)
    best_text = _best_text_by_heading_evidence(text_by_node)
    metrics = _text_quality_metrics(all_text)

    return {
        "law_id": law_id,
        "selector": selector,
        "selector_exists": bool(nodes),
        "node_count": len(nodes),
        "first_node_text_length": len(first_text),
        "all_nodes_concat_text_length": len(all_text),
        "best_node_text_length": len(best_text),
        "article_reference_count": metrics["article_reference_count"],
        "article_heading_count": metrics["article_heading_count"],
        "max_heading_article_number": metrics["max_heading_article_number"],
        "has_heading_article_1": metrics["has_heading_article_1"],
        "heading_sequence_score": metrics["heading_sequence_score"],
        "duplicate_line_ratio": metrics["duplicate_line_ratio"],
        "estimated_noise_score": _estimated_noise_score(all_text),
    }


def _best_text_by_heading_evidence(texts: list[str]) -> str:
    best_text = ""
    best_score = -1.0
    for text in texts:
        metrics = _text_quality_metrics(text)
        score = (
            metrics["article_heading_count"] * 1000
            + metrics["heading_sequence_score"] * 100
            + min(len(text), 100_000) / 1000
        )
        if score > best_score:
            best_score = score
            best_text = text
    return best_text


def _text_quality_metrics(text: str) -> dict[str, Any]:
    reference_numbers = _article_numbers(ARTICLE_REFERENCE_RE, text)
    heading_numbers = _article_numbers(ARTICLE_HEADING_RE, text)
    return {
        "article_reference_count": len(reference_numbers),
        "article_heading_count": len(heading_numbers),
        "max_article_reference_number": max(reference_numbers) if reference_numbers else 0,
        "max_heading_article_number": max(heading_numbers) if heading_numbers else 0,
        "has_reference_article_1": 1 in reference_numbers,
        "has_heading_article_1": 1 in heading_numbers,
        "heading_sequence_score": _sequence_score(heading_numbers),
        "duplicate_line_ratio": _duplicate_line_ratio(text),
        "broken_article_heading_count": len(BROKEN_ARTICLE_HEADING_RE.findall(text)),
        "split_vietnamese_word_count": _split_vietnamese_word_count(text),
    }


def _article_numbers(pattern: re.Pattern[str], text: str) -> list[int]:
    numbers: list[int] = []
    for match in pattern.finditer(text):
        try:
            numbers.append(int(match.group(1)))
        except (IndexError, ValueError):
            continue
    return numbers


def _sequence_score(numbers: list[int]) -> float:
    unique_numbers = sorted(set(numbers))
    if not unique_numbers:
        return 0.0
    max_number = unique_numbers[-1]
    return len(unique_numbers) / max_number if max_number else 0.0


def _duplicate_line_ratio(text: str) -> float:
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 12]
    if not lines:
        return 0.0
    counts = Counter(lines)
    duplicate_lines = sum(count - 1 for count in counts.values() if count > 1)
    return round(duplicate_lines / len(lines), 4)


def _split_vietnamese_word_count(text: str) -> int:
    return sum(len(pattern.findall(text)) for pattern in SPLIT_VIETNAMESE_WORD_PATTERNS)


def _estimated_noise_score(text: str) -> float:
    if not text:
        return 0.0
    noise_hits = sum(text.lower().count(marker.lower()) for marker in START_NOISE_MARKERS + END_NOISE_MARKERS)
    duplicate_penalty = _duplicate_line_ratio(text)
    article_count = len(ARTICLE_HEADING_RE.findall(text))
    density_penalty = 1.0 if article_count == 0 and len(text) > 1000 else 0.0
    score = min(1.0, (noise_hits * 0.08) + duplicate_penalty + density_penalty)
    return round(score, 4)


def _marker_counts(text: str) -> dict[str, int]:
    return {
        "article_references": len(ARTICLE_REFERENCE_RE.findall(text)),
        "article_headings": len(ARTICLE_HEADING_RE.findall(text)),
        "clause_headings": len(CLAUSE_HEADING_RE.findall(text)),
        "point_headings": len(POINT_HEADING_RE.findall(text)),
        "chapter_references": len(re.findall(r"\bChương\b", text, re.IGNORECASE)),
        "section_references": len(re.findall(r"\bMục\b", text, re.IGNORECASE)),
        "part_references": len(re.findall(r"\bPhần\b", text, re.IGNORECASE)),
    }


def _cleaning_suspicious_flags(text: str, metrics: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if len(text) < 5000:
        flags.append("short_normalized_text")
    if metrics["article_heading_count"] == 0:
        flags.append("missing_article_headings")
    if not metrics["has_heading_article_1"]:
        flags.append("missing_article_1_heading")
    if metrics["duplicate_line_ratio"] > 0.20:
        flags.append("high_duplicate_line_ratio")
    if metrics["broken_article_heading_count"] > 0:
        flags.append("broken_article_heading")
    if metrics["split_vietnamese_word_count"] > 0:
        flags.append("split_vietnamese_words")
    if _has_wrong_start(text):
        flags.append("possible_wrong_start")
    if _has_wrong_end(text):
        flags.append("possible_wrong_end")
    return flags


def _possible_missing_body(
    raw_metrics: dict[str, Any],
    cleaned_metrics: dict[str, Any],
    cleaned_chars: int,
) -> bool:
    if cleaned_chars < 5000 and raw_metrics["article_reference_count"] >= 5:
        return True
    if raw_metrics["max_article_reference_number"] >= 20 and cleaned_metrics["max_heading_article_number"] < 3:
        return True
    return False


def _has_wrong_start(text: str) -> bool:
    first_lines = "\n".join([line.strip() for line in text.splitlines()[:20] if line.strip()])
    return any(marker.lower() in first_lines.lower() for marker in START_NOISE_MARKERS)


def _has_wrong_end(text: str) -> bool:
    tail_lines = "\n".join([line.strip() for line in text.splitlines()[-40:] if line.strip()])
    return any(marker.lower() in tail_lines.lower() for marker in END_NOISE_MARKERS)


def _normalized_max_article(normalized_path: Path) -> int:
    if not normalized_path.is_file():
        return 0
    data = _load_json(normalized_path)
    text = str(data.get("normalized_text") or "")
    return int(_text_quality_metrics(text)["max_heading_article_number"])


def _classify_pattern_group(law_id: str, name: str, source_type: str, max_article: int) -> str:
    normalized = f"{law_id} {name} {source_type}".lower()
    is_consolidated = "vbhn" in normalized or "hợp nhất" in normalized
    is_large_code = "bộ luật" in normalized or max_article >= 200
    is_organization = any(
        phrase in normalized
        for phrase in (
            "tổ chức",
            "quốc hội",
            "chính phủ",
            "tòa án",
            "toà án",
            "viện kiểm sát",
            "chính quyền địa phương",
        )
    )

    if "hiến pháp" in normalized or law_id.upper().startswith("HP"):
        return "Constitution"
    if is_organization:
        return "Government/judiciary organization laws"
    if is_consolidated and is_large_code:
        return "Consolidated large codes"
    if is_large_code:
        return "Original large code"
    if is_consolidated:
        return "Consolidated ordinary laws"
    if "luật" in normalized:
        return "Original ordinary laws"
    return "Other"


def _first_position(text: str, patterns: tuple[str, ...]) -> int | None:
    positions = [match.start() for pattern in patterns if (match := re.search(pattern, text))]
    return min(positions) if positions else None


def _find_or_none(text: str, marker: str) -> int | None:
    position = text.find(marker)
    return position if position != -1 else None
