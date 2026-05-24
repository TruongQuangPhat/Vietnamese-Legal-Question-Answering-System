from __future__ import annotations

import json
import re
import unicodedata
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from bs4 import BeautifulSoup

from src.ingestion.audit import scan_raw_artifacts

# --- Constants ---

LEGAL_MARKERS_KEYWORDS = {"điều", "khoản", "điểm", "luật", "bộ luật", "văn bản hợp nhất", "quốc hội", "căn cứ"}
STRONG_LEGAL_MARKERS = {"Điều", "Chương", "Mục", "Phần", "Văn bản hợp nhất", "QUỐC HỘI", "Căn cứ", "Bộ luật", "Luật"}

SAFE_BOILERPLATE = {
    "THƯ VIỆN PHÁP LUẬT",
    "Đăng nhập",
    "Đăng ký",
    "Tra cứu pháp luật",
    "Hotline",
    "Liên hệ",
    "Tải về",
    "Văn bản liên quan",
    "Lược đồ",
    "Nội dung MIX",
    "Quảng cáo",
}

# Regex patterns for legal structure
RE_ARTICLE = re.compile(r"Điều\s+\d+", re.IGNORECASE)
RE_CLAUSE = re.compile(r"^\s*\d+\..+")
RE_POINT = re.compile(r"^\s*[a-zđ]\).+", re.IGNORECASE)

# Unicode handling
REPLACEMENT_CHAR = "�"
NBSP = " "
ZERO_WIDTH_CHARS = {
    "​",  # zero-width space
    "‌",  # zero-width non-joiner
    "‍",  # zero-width joiner
    "﻿",  # BOM
}

@dataclass
class CleaningStats:
    """Text statistics for a normalized document."""
    raw_html_size_bytes: int = 0
    extracted_text_chars: int = 0
    normalized_text_chars: int = 0
    line_count: int = 0

@dataclass
class LegalMarkersSummary:
    """Summary of legal markers found in the text."""
    contains_part: bool = False
    contains_chapter: bool = False
    contains_section: bool = False
    contains_article: bool = False
    contains_clause_numbering: bool = False
    contains_point_labeling: bool = False
    article_count_estimate: int = 0

@dataclass
class NormalizedArtifact:
    """The final normalized output for a single legal document."""
    law_id: str
    law_name: str
    source_url: str
    source_domain: str
    source_type: str
    raw_artifact_path: str
    normalized_text: str
    text_stats: CleaningStats
    markers: LegalMarkersSummary
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=lambda: {"cleaner_version": "v0.3"})

    def to_dict(self) -> Dict:
        return {
            "law_id": self.law_id,
            "law_name": self.law_name,
            "source_url": self.source_url,
            "source_domain": self.source_domain,
            "source_type": self.source_type,
            "raw_artifact_path": self.raw_artifact_path,
            "normalized_text": self.normalized_text,
            "text_stats": {
                "raw_html_size_bytes": self.text_stats.raw_html_size_bytes,
                "extracted_text_chars": self.text_stats.extracted_text_chars,
                "normalized_text_chars": self.text_stats.normalized_text_chars,
                "line_count": self.text_stats.line_count,
            },
            "markers": {
                "contains_part": self.markers.contains_part,
                "contains_chapter": self.markers.contains_chapter,
                "contains_section": self.markers.contains_section,
                "contains_article": self.markers.contains_article,
                "contains_clause_numbering": self.markers.contains_clause_numbering,
                "contains_point_labeling": self.markers.contains_point_labeling,
                "article_count_estimate": self.markers.article_count_estimate,
            },
            "warnings": self.warnings,
            "metadata": self.metadata,
        }

def extract_legal_text_from_html(html_content: str) -> str:
    """Extracts the best legal content container from HTML using scoring.

    Args:
        html_content: Raw HTML string.

    Returns:
        Extracted text from the best candidate container.
    """
    # Parser strategy: lxml -> html5lib -> html.parser
    parser_options = ["lxml", "html5lib", "html.parser"]
    soup = None
    for p in parser_options:
        try:
            soup = BeautifulSoup(html_content, p)
            break
        except Exception:
            continue

    if soup is None:
        return ""

    # 1. Decompose known noisy elements (Do NOT decompose 'form')
    skip_tags = {
        "script", "style", "noscript", "iframe",
        "button", "select", "input", "svg"
    }
    for tag in soup.find_all(skip_tags):
        tag.decompose()

    # 2. Candidate scoring to find the main content container
    # We consider block-level containers but not body (as fallback only)
    candidates = soup.find_all(['div', 'article', 'main', 'section', 'td'])

    best_candidate = None
    max_score = -1.0

    for candidate in candidates:
        # Fast extraction of text for scoring
        text = candidate.get_text(separator=" ", strip=True)
        if not text:
            continue

        text_len = len(text)

        # Quick check for any legal marker
        if not any(m in text for m in ('Điều', 'Chương', 'Mục')):
            continue

        # Count legal markers
        dieu_count = len(RE_ARTICLE.findall(text))
        chapter_count = len(re.findall(r'Chương\s+[IVXLCDM]+', text, re.I))
        muc_count = text.count("Mục")
        luat_count = text.count("Luật") + text.count("Bộ luật")
        quoc_hoi = 1 if "QUỐC HỘI" in text else 0
        can_cu = 1 if "Căn cứ" in text else 0

        # Base score with strong weighting for markers, scaled by text density
        marker_sum = dieu_count + chapter_count + muc_count
        marker_benefit = (
            dieu_count * 10000 +
            chapter_count * 5000 +
            muc_count * 2000 +
            luat_count * 1000 +
            quoc_hoi * 5000 +
            can_cu * 5000
        )

        # Scaling factor: reduce benefit if average text per marker is too low (likely nav/TOC)
        # We expect at least 150 chars per legal marker for it to be actual content
        density_factor = 1.0
        if marker_sum > 0:
            density_factor = min(1.0, text_len / (marker_sum * 150))

        score = text_len + (marker_benefit * density_factor)


        # Penalize high link density and few legal markers
        link_count = len(candidate.find_all('a'))
        if link_count > 5 and dieu_count < 3:
            score *= 0.5

        if score > max_score:
            max_score = score
            best_candidate = candidate

    if best_candidate:
        return best_candidate.get_text(separator="\n")

    # Fallback: use body text
    body = soup.body
    if body:
        return body.get_text(separator="\n")
    return soup.get_text(separator="\n")

def remove_safe_boilerplate(text: str) -> str:
    """Removes repeated non-legal boilerplate patterns conservatively.

    Preserves lines containing strong legal markers or structural numbering.
    """
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue

        # 1. Never remove lines containing strong legal markers
        if any(marker in stripped for marker in STRONG_LEGAL_MARKERS):
            cleaned_lines.append(line)
            continue

        # 2. Never remove numbered clause lines (e.g., "1. Nội dung")
        if RE_CLAUSE.match(stripped):
            cleaned_lines.append(line)
            continue

        # 3. Never remove point labels (e.g., "a) Nội dung")
        if RE_POINT.match(stripped):
            cleaned_lines.append(line)
            continue

        # 4. Remove bare numbering (e.g., "1." or "a)") without content
        if re.match(r"^\s*\d+\.\s*$", stripped) or re.match(r"^\s*[a-zđ]\)\s*$", stripped, re.I):
            continue

        # 5. Remove if the line matches a known boilerplate phrase exactly
        if any(bp == stripped for bp in SAFE_BOILERPLATE):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)

def normalize_unicode(text: str) -> Tuple[str, List[str]]:
    """Applies NFC normalization and removes unwanted characters.

    Returns:
        Tuple of (normalized_text, warnings).
    """
    warnings = []

    # 1. Decode HTML entities
    text = html.unescape(text)

    # 2. NFC Normalization
    text = unicodedata.normalize("NFC", text)

    # 3. Check for Unicode replacement character U+FFFD
    if REPLACEMENT_CHAR in text:
        warnings.append("encoding_replacement_character_found")

    # 4. Normalize NBSP to regular space
    text = text.replace(NBSP, " ")

    # 5. Remove zero-width characters
    for char in ZERO_WIDTH_CHARS:
        text = text.replace(char, "")

    # 6. Remove invalid control characters (C0 except \n, \r, \t)
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\r\t")

    return text, warnings

def normalize_whitespace(text: str) -> str:
    """Collapses excessive whitespace while preserving legal boundaries."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "    ")

    lines = text.splitlines()
    normalized_lines = []

    for line in lines:
        stripped = line.strip()
        collapsed = re.sub(r"[ \t]+", " ", stripped)
        if collapsed:
            normalized_lines.append(collapsed)
        else:
            normalized_lines.append("")

    final_lines = []
    blank_count = 0
    for line in normalized_lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)

    return "\n".join(final_lines)

def detect_legal_markers(text: str) -> LegalMarkersSummary:
    """Detects legal hierarchy markers and estimates article count."""
    summary = LegalMarkersSummary()

    summary.contains_part = "Phần" in text
    summary.contains_chapter = "Chương" in text
    summary.contains_section = "Mục" in text
    summary.contains_article = bool(RE_ARTICLE.search(text))

    lines = text.splitlines()
    for line in lines:
        if RE_CLAUSE.match(line):
            summary.contains_clause_numbering = True
        if RE_POINT.match(line):
            summary.contains_point_labeling = True

    summary.article_count_estimate = len(RE_ARTICLE.findall(text))

    return summary

def load_raw_metadata(metadata_path: Path) -> Dict:
    """Loads metadata from JSON file."""
    with metadata_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def clean_raw_artifact(
    artifact_paths: Tuple[Path, Path],
    output_dir: Path,
    min_text_length: int,
    write_txt: bool
) -> Tuple[Optional[NormalizedArtifact], List[str]]:
    """Cleans a single raw legal artifact."""
    main_html_path, metadata_json_path = artifact_paths
    law_id = main_html_path.parent.name
    if "latest" in main_html_path.parts:
        law_id = main_html_path.parent.parent.name

    try:
        meta = load_raw_metadata(metadata_json_path)
        raw_html_size = main_html_path.stat().st_size

        with main_html_path.open("r", encoding="utf-8") as f:
            html_content = f.read()

        extracted_text = extract_legal_text_from_html(html_content)
        extracted_chars = len(extracted_text)

        text = remove_safe_boilerplate(extracted_text)
        text, uni_warnings = normalize_unicode(text)
        text = normalize_whitespace(text)

        markers = detect_legal_markers(text)

        stats = CleaningStats(
            raw_html_size_bytes=raw_html_size,
            extracted_text_chars=extracted_chars,
            normalized_text_chars=len(text),
            line_count=len(text.splitlines())
        )

        warnings = list(uni_warnings)
        if len(text) < min_text_length:
            warnings.append("text_suspiciously_short")
        if not markers.contains_article:
            warnings.append("missing_article_marker")

        artifact = NormalizedArtifact(
            law_id=meta.get("law_id", law_id),
            law_name=meta.get("name", meta.get("law_name", "Unknown")),
            source_url=meta.get("url", meta.get("source_url", "Unknown")),
            source_domain=meta.get("source_domain", "Unknown"),
            source_type=meta.get("source_type", "Unknown"),
            raw_artifact_path=str(main_html_path),
            normalized_text=text,
            text_stats=stats,
            markers=markers,
            warnings=warnings
        )

        law_out_dir = output_dir / artifact.law_id
        law_out_dir.mkdir(parents=True, exist_ok=True)

        with (law_out_dir / "normalized.json").open("w", encoding="utf-8") as f:
            json.dump(artifact.to_dict(), f, indent=2, ensure_ascii=False)

        if write_txt:
            with (law_out_dir / "cleaned.txt").open("w", encoding="utf-8") as f:
                f.write(artifact.normalized_text)

        return artifact, []

    except Exception as e:
        return None, [str(e)]

def clean_raw_corpus(
    raw_dir: Path,
    output_dir: Path,
    min_text_length: int,
    write_txt: bool
) -> Dict:
    """Processes the entire raw corpus."""
    artifacts = scan_raw_artifacts(raw_dir)

    results = []
    summary = {
        "total_artifacts": len(artifacts),
        "successfully_cleaned": 0,
        "warning_artifacts": 0,
        "failed": 0,
        "suspiciously_short_texts": 0,
        "missing_article_marker": 0,
        "output_dir": str(output_dir)
    }

    for law_id, artifact_dir in sorted(artifacts.items()):
        main_html = artifact_dir / "main.html"
        meta_json = artifact_dir / "metadata.json"

        artifact, errors = clean_raw_artifact(
            (main_html, meta_json),
            output_dir,
            min_text_length,
            write_txt
        )

        if artifact:
            summary["successfully_cleaned"] += 1
            status = "success"
            if artifact.warnings:
                status = "warning"
                summary["warning_artifacts"] += 1

            if "text_suspiciously_short" in artifact.warnings:
                summary["suspiciously_short_texts"] += 1
            if "missing_article_marker" in artifact.warnings:
                summary["missing_article_marker"] += 1

            results.append({
                "law_id": artifact.law_id,
                "status": status,
                "output_path": str(output_dir / artifact.law_id / "normalized.json"),
                "normalized_text_chars": artifact.text_stats.normalized_text_chars,
                "line_count": artifact.text_stats.line_count,
                "article_count_estimate": artifact.markers.article_count_estimate,
                "warnings": artifact.warnings,
                "errors": []
            })
        else:
            summary["failed"] += 1
            results.append({
                "law_id": law_id,
                "status": "failed",
                "output_path": None,
                "normalized_text_chars": 0,
                "line_count": 0,
                "article_count_estimate": 0,
                "warnings": [],
                "errors": errors
            })

    return {
        "summary": summary,
        "items": results
    }

def write_cleaning_report(report: Dict, report_path: Path) -> None:
    """Writes the final cleaning report to JSON."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
