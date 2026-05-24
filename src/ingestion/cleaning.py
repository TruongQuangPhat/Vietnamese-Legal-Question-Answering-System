from __future__ import annotations

import json
import re
import unicodedata
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from html.parser import HTMLParser

from src.ingestion.audit import scan_raw_artifacts

# --- Constants ---

LEGAL_MARKERS_KEYWORDS = {"điều", "khoản", "điểm", "luật", "bộ luật", "văn bản hợp nhất", "quốc hội", "căn cứ"}
STRONG_LEGAL_MARKERS = {"Điều", "Chương", "Mục", "Phần", "Văn bản hợp nhất", "QUỐC HỘI", "Căn cứ"}

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
RE_CLAUSE = re.compile(r"^\s*\d+\.")
RE_POINT = re.compile(r"^\s*[a-zđ]\)")

# Unicode removal targets
ZERO_WIDTH_CHARS = {
    "​", # zero-width space
    "‌", # zero-width non-joiner
    "‍", # zero-width joiner
    "﻿", # BOM
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
    metadata: Dict[str, str] = field(default_factory=lambda: {"cleaner_version": "v0.1"})

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

class LegalTextExtractor(HTMLParser):
    """Deterministic HTML extractor for legal text.

    Removes scripts, styles, and non-content elements while preserving
    basic line structure.
    """
    # Void elements: no closing tag, cannot contain content
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr"
    }

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: List[str] = []
        self.skip_tags: Set[str] = {
            "script", "style", "noscript", "iframe", "svg"
        }
        self.ignore_stack: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        # Void tags have no content; ignore them entirely
        if tag in self.VOID_TAGS:
            return
        if tag in self.skip_tags:
            self.ignore_stack.append(tag)
            return
        # Handle hidden elements via style attribute
        for attr, val in attrs:
            if attr == "style" and val and "display:none" in val.lower():
                self.ignore_stack.append(tag)
                break

    def handle_endtag(self, tag: str) -> None:
        if tag in self.ignore_stack:
            # Robust pop: remove everything up to the matching start tag
            while self.ignore_stack:
                popped = self.ignore_stack.pop()
                if popped == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self.ignore_stack:
            # Preserve a newline for common block-level elements
            # (implemented in the wrapper function).
            self.text_parts.append(data)

    def get_text(self) -> str:
        return "".join(self.text_parts)

def extract_legal_text_from_html(html_content: str) -> str:
    """Extracts visible text from HTML while removing non-content elements.

    Args:
        html_content: Raw HTML string.

    Returns:
        Extracted text with basic structure preserved.
    """
    # 1. Remove large blocks that are likely to be imbalanced or not contain legal text
    # Use DOTALL to match across newlines
    for pattern in [
        (r"<script.*?>.*?</script>", ""),
        (r"<style.*?>.*?</style>", ""),
        (r"<noscript.*?>.*?</noscript>", ""),
        (r"<iframe.*?>.*?</iframe>", ""),
        (r"<svg.*?>.*?</svg>", ""),
    ]:
        html_content = re.sub(pattern[0], pattern[1], html_content, flags=re.DOTALL | re.IGNORECASE)

    # 2. To preserve some structure, we manually add newlines before block-level tags
    processed_html = html_content.replace("</div>", "</div>\n")
    processed_html = processed_html.replace("</p>", "</p>\n")
    processed_html = processed_html.replace("</tr>", "</tr>\n")
    processed_html = processed_html.replace("</h1>", "</h1>\n")
    processed_html = processed_html.replace("</h2>", "</h2>\n")
    processed_html = processed_html.replace("</h3>", "</h3>\n")
    processed_html = processed_html.replace("</h4>", "</h4>\n")
    processed_html = processed_html.replace("<li>", "\n<li>")

    parser = LegalTextExtractor()
    parser.feed(processed_html)
    return parser.get_text()

def remove_safe_boilerplate(text: str) -> str:
    """Removes repeated non-legal boilerplate patterns.

    Preserves lines containing strong legal markers.
    """
    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append(line)
            continue

        # Rule: Never remove lines containing strong legal markers
        if any(marker in stripped for marker in STRONG_LEGAL_MARKERS):
            cleaned_lines.append(line)
            continue

        # Remove if the line matches a known boilerplate phrase exactly or is a subset
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

    # 3. Check for replacement character
    if "�" in text:
        warnings.append("encoding_replacement_character_found")

    # 4. Remove NBSP and other targets
    text = text.replace(" ", " ") # NBSP -> space

    for char in ZERO_WIDTH_CHARS:
        text = text.replace(char, "")

    # 5. Remove invalid control characters (C0 except \n, \r, \t)
    # This keeps the text clean for downstream regex.
    text = "".join(ch for ch in text if ord(ch) >= 32 or ch in "\n\r\t")

    return text, warnings

def normalize_whitespace(text: str) -> str:
    """Collapses excessive whitespace while preserving legal boundaries.

    Returns:
        Normalized text.
    """
    # \r\n and \r to \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Tabs to spaces
    text = text.replace("\t", "    ")

    lines = text.splitlines()
    normalized_lines = []

    for line in lines:
        # Strip leading/trailing whitespace
        stripped = line.strip()

        # Collapse repeated spaces within each line
        # But preserve leading spaces if they are part of a known pattern?
        # No, the requirement says "strip leading/trailing whitespace on each line".
        collapsed = re.sub(r"[ \t]+", " ", stripped)

        if collapsed:
            normalized_lines.append(collapsed)
        else:
            # Preserve single blank lines as paragraph breaks
            normalized_lines.append("")

    # Collapse excessive blank lines (more than 2)
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
    """Detects legal hierarchy markers and estimates article count.

    Args:
        text: Normalized legal text.

    Returns:
        LegalMarkersSummary object.
    """
    summary = LegalMarkersSummary()

    # Simple keyword detection
    summary.contains_part = "Phần" in text
    summary.contains_chapter = "Chương" in text
    summary.contains_section = "Mục" in text
    summary.contains_article = bool(RE_ARTICLE.search(text))

    # Pattern detection for clauses and points
    lines = text.splitlines()
    for line in lines:
        if RE_CLAUSE.match(line):
            summary.contains_clause_numbering = True
        if RE_POINT.match(line):
            summary.contains_point_labeling = True

    # Estimate article count
    summary.article_count_estimate = len(RE_ARTICLE.findall(text))

    return summary

def load_raw_metadata(metadata_path: Path) -> Dict:
    """Loads metadata from JSON file.

    Args:
        metadata_path: Path to metadata.json

    Returns:
        Metadata dictionary.
    """
    with metadata_path.open("r", encoding="utf-8") as f:
        return json.load(f)

def clean_raw_artifact(
    artifact_paths: Tuple[Path, Path],
    output_dir: Path,
    min_text_length: int,
    write_txt: bool
) -> Tuple[NormalizedArtifact, List[str]]:
    """Cleans a single raw legal artifact.

    Args:
        artifact_paths: Tuple of (main_html_path, metadata_json_path).
        output_dir: Base output directory.
        min_text_length: Length threshold for warnings.
        write_txt: Whether to write debug .txt file.

    Returns:
        Tuple of (NormalizedArtifact, errors).
    """
    main_html_path, metadata_json_path = artifact_paths
    law_id = main_html_path.parent.name
    if "latest" in main_html_path.parts:
        # If layout is {law_id}/latest/main.html, the parent is 'latest'.
        # We need the grandparent.
        law_id = main_html_path.parent.parent.name

    try:
        # 1. Metadata
        meta = load_raw_metadata(metadata_json_path)

        # 2. HTML Extraction
        raw_html_size = main_html_path.stat().st_size
        with main_html_path.open("r", encoding="utf-8") as f:
            html_content = f.read()

        extracted_text = extract_legal_text_from_html(html_content)
        extracted_chars = len(extracted_text)

        # 3. Cleaning Pipeline
        text = remove_safe_boilerplate(extracted_text)
        text, uni_warnings = normalize_unicode(text)
        text = normalize_whitespace(text)

        # 4. Markers
        markers = detect_legal_markers(text)

        # 5. Build Artifact
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

        # Write outputs
        law_out_dir = output_dir / artifact.law_id
        law_out_dir.mkdir(parents=True, exist_ok=True)

        # normalized.json
        with (law_out_dir / "normalized.json").open("w", encoding="utf-8") as f:
            json.dump(artifact.to_dict(), f, indent=2, ensure_ascii=False)

        # cleaned.txt (optional)
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
    """Processes the entire raw corpus.

    Returns:
        The final cleaning report.
    """
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
    """Writes the final cleaning report to JSON.

    Args:
        report: The report dictionary.
        report_path: Output path for the report.
    """
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)