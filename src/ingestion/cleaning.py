from __future__ import annotations

import json
import re
import unicodedata
import html
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any
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
RE_CLAUSE = re.compile(r"^\s*\d+\..+")  # require some text after "1."
RE_POINT = re.compile(r"^\s*[a-zđ]\).+", re.IGNORECASE)

# Boundary trimming markers
START_MARKERS = [
    (re.compile(r"QUỐC HỘI.*CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", re.S | re.I), 10),
    (re.compile(r"(?m)^\s*VĂN BẢN HỢP NHẤT\b", re.I), 8),
    (re.compile(r"(?m)^\s*HIẾN PHÁP\b", re.I), 7),
    (re.compile(r"(?m)^\s*BỘ LUẬT\b", re.I), 6),
    (re.compile(r"(?m)^\s*LUẬT\s+[A-ZÀ-Ỵ]", re.I), 5),
    (re.compile(r"(?m)^\s*LỜI NÓI ĐẦU\b", re.I), 4),
    (re.compile(r"(?m)^\s*Chương\s+I\b", re.I), 3),
    (re.compile(r"(?m)^\s*Điều\s+1\.", re.I), 2),
]
END_MARKERS = [
    "Văn bản liên quan",
    "Liên quan hiệu lực",
    "Liên quan nội dung",
    "Thuộc tính",
    "Tải về",
    "Đăng nhập để sử dụng tiện ích",
    "Bình luận",
    "Hỏi đáp",
    "Tin liên quan",
]

# Candidate scoring penalties
BAD_ID_CLASS = {
    'nav', 'navigation', 'menu', 'sidebar', 'header', 'footer', 'search', 'login',
    'dangnhap', 'dangky', 'tracuu', 'danhmuc', 'hotro', 'widget', 'tukhoa', 'tomtat'
}
METADATA_ID_CLASS = {
    'tab', 'tabs', 'tooltip', 'related', 'relation', 'lienquan', 'lien-quan',
    'hieuluc', 'hieu-luc', 'thuoc-tinh', 'thuoctinh', 'metadata', 'popup', 'modal'
}
SITE_NOISE_PHRASES = {
    'Đăng nhập', 'Đăng ký', 'Tra cứu', 'Danh mục', 'Hỗ trợ', 'Dịch vụ', 'Google',
    'Widget', 'Từ khóa', 'Tóm tắt nội dung', 'Liên quan hiệu lực', 'Liên quan nội dung',
    'Thuộc tính', 'Xem chi tiết', 'Văn bản liên quan', 'Văn bản gốc',
    'CÁC NỘI DUNG ĐƯỢC SỬA ĐỔI, HƯỚNG DẪN', 'Tra cứu nhanh', 'Hỗ trợ Dịch Vụ'
}

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
    metadata: Dict[str, str] = field(default_factory=lambda: {"cleaner_version": "v0.4"})
    candidate_info: Dict[str, Any] = field(default_factory=dict)

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
            "candidate_info": self.candidate_info,
        }

def extract_legal_text_from_html(html_content: str) -> Tuple[str, Dict[str, Any]]:
    """Extracts the best legal content container from HTML using scoring.

    Args:
        html_content: Raw HTML string.

    Returns:
        Tuple of (extracted text, candidate info).
    """
    parser_options = ["lxml", "html5lib", "html.parser"]
    soup = None
    for p in parser_options:
        try:
            soup = BeautifulSoup(html_content, p)
            break
        except Exception:
            continue

    if soup is None:
        return "", {"tag": None, "class": [], "id": "", "marker_sum": 0, "text_len": 0}

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
    best_score = -float('inf')

    # Terms that indicate navigation/site chrome containers
    BAD_ID_CLASS = {
        'nav', 'navigation', 'menu', 'sidebar', 'header', 'footer', 'search', 'login',
        'dangnhap', 'dangky', 'tracuu', 'danhmuc', 'hotro', 'widget', 'tukhoa', 'tomtat'
    }
    # Terms that indicate metadata/tabs/tooltips (higher penalty)
    METADATA_ID_CLASS = {
        'tab', 'tabs', 'tooltip', 'related', 'relation', 'lienquan', 'lien-quan',
        'hieuluc', 'hieu-luc', 'thuoc-tinh', 'thuoctinh', 'metadata', 'popup', 'modal'
    }
    SITE_NOISE_PHRASES = {
        'Đăng nhập', 'Đăng ký', 'Tra cứu', 'Danh mục', 'Hỗ trợ', 'Dịch vụ', 'Google',
        'Widget', 'Từ khóa', 'Tóm tắt nội dung', 'Liên quan hiệu lực', 'Liên quan nội dung',
        'Thuộc tính', 'Xem chi tiết', 'Văn bản liên quan', 'Văn bản gốc',
        'CÁC NỘI DUNG ĐƯỢC SỬA ĐỔI, HƯỚNG DẪN', 'Tra cứu nhanh', 'Hỗ trợ Dịch Vụ'
    }


    for candidate in candidates:
        text = candidate.get_text(separator="\n", strip=True)
        if not text:
            continue

        # Quick check for any legal marker
        if not any(m in text for m in ('Điều', 'Chương', 'Mục')):
            continue

        # Count legal markers
        dieu_count = len(RE_ARTICLE.findall(text))
        chapter_count = len(re.findall(r'Chương\s+[IVXLCDM]+', text, re.I))
        muc_count = text.count("Mục")
        marker_sum = dieu_count + chapter_count + muc_count

        text_len = len(text)

        # Skip if no substantial legal markers
        if marker_sum == 0:
            continue

        # Base score: reward markers and length
        score = marker_sum * 1000 + text_len

        # 1. Penalize link density (Corrected order)
        link_count = len(candidate.find_all('a'))
        link_text_len = sum(len(a.get_text(strip=True)) for a in candidate.find_all('a') if a.get_text(strip=True))
        link_density = link_text_len / text_len if text_len > 0 else 0
        if link_density > 0.5:
            score *= 0.2
        elif link_density > 0.3:
            score *= 0.5

        # 2. Penalize/Reward content density per article
        avg_chars_per_marker = text_len / marker_sum
        if avg_chars_per_marker < 50:
            score *= 0.3
        elif avg_chars_per_marker >= 100:
            score *= 1.2

        # 3. Penalize bad id/class names
        candidate_id = (candidate.get('id') or '').lower()
        candidate_class = ' '.join(candidate.get('class') or []).lower()

        # Strong penalty for metadata/tabs/tooltips
        if any(bad in candidate_id or bad in candidate_class for bad in METADATA_ID_CLASS):
            score *= 0.1
        # Standard penalty for nav/chrome
        elif any(bad in candidate_id or bad in candidate_class for bad in BAD_ID_CLASS):
            score *= 0.3

        # 4. Penalize site noise phrases
        noise_count = sum(1 for phrase in SITE_NOISE_PHRASES if phrase.lower() in text.lower())
        if noise_count > 2:
            score *= 0.5

        # Debug: record scores for analysis
        # (could be logged if needed)

        if score > best_score:
            best_score = score
            best_candidate = candidate

    if best_candidate:
        # Recalculate detailed stats for the selected candidate
        final_text = best_candidate.get_text(separator="\n")
        final_dieu = len(RE_ARTICLE.findall(final_text))
        final_chapter = len(re.findall(r'Chương\s+[IVXLCDM]+', final_text, re.I))
        final_muc = final_text.count("Mục")
        link_count = len(best_candidate.find_all('a'))
        link_text_len = sum(len(a.get_text(strip=True)) for a in best_candidate.find_all('a') if a.get_text(strip=True))
        link_density = link_text_len / len(final_text) if final_text else 0

        candidate_info = {
            "tag": best_candidate.name,
            "class": best_candidate.get("class", []),
            "id": best_candidate.get("id", ""),
            "article_count": final_dieu,
            "chapter_count": final_chapter,
            "section_count": final_muc,
            "text_len": len(final_text),
            "link_density": link_density,
            "avg_chars_per_article": len(final_text) / (final_dieu + 1),
        }
        return final_text, candidate_info

    # Fallback: use body text
    body = soup.body
    if body:
        text = body.get_text(separator="\n")
        return text, {"tag": "body", "class": [], "id": "", "article_count": 0, "chapter_count": 0, "section_count": 0, "text_len": len(text), "link_density": 0, "avg_chars_per_article": 0}
    text = soup.get_text(separator="\n")
    return text, {"tag": "soup", "class": [], "id": "", "article_count": 0, "chapter_count": 0, "section_count": 0, "text_len": len(text), "link_density": 0, "avg_chars_per_article": 0}

def trim_to_legal_body(text: str) -> str:
    """Trims website chrome from the beginning and end of extracted text.

    Uses reliable legal headers to find the start of the actual legal document.
    Only applies end trimming after confirming substantial legal body content.

    Args:
        text: Extracted text from HTML.

    Returns:
        Trimmed text starting from the legal body.
    """
    original = text.lstrip()

    # 1. Find start using reliable markers with validation
    start_pos = _find_legal_body_start(original)
    if start_pos < len(original):
        text = original[start_pos:]
    else:
        text = original

    # 2. Trim trailing post-body noise only after confirming body exists
    text = _trim_trailing_noise(text)

    return text

def _find_legal_body_start(text: str) -> int:
    """Finds the start position of the legal body using context-aware markers.

    Returns character index or len(text) if no reliable start found.
    """
    # Try markers in order of reliability (high to low)
    for pattern, _ in START_MARKERS:
        m = pattern.search(text)
        if m:
            pos = m.start()
            # Validate: after this marker, there should be evidence of a legal body
            after_text = text[pos:]
            if _has_sufficient_legal_evidence(after_text, min_articles=2, min_chars=500):
                return pos
    return len(text)

def _has_sufficient_legal_evidence(text: str, min_articles: int, min_chars: int) -> bool:
    """Checks if text contains enough legal structure to confirm it's the real body."""
    # Count article markers
    article_count = len(RE_ARTICLE.findall(text))
    if article_count < min_articles:
        return False
    # Also check total length
    if len(text) < min_chars:
        return False
    return True

def _trim_trailing_noise(text: str) -> str:
    """Trims trailing website chrome only after confirming legal body is present."""
    lines = text.splitlines()

    # First, confirm we have enough legal body content before considering trimming
    body_start_idx = None
    legal_articles_seen = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if RE_ARTICLE.search(stripped):
            legal_articles_seen += 1
            if body_start_idx is None:
                body_start_idx = i
        # Require at least 3 articles before we trust the body has started
        if legal_articles_seen >= 3:
            break

    if body_start_idx is None:
        # No clear legal body found; don't trim
        return text

    # Now look for end markers, but only after we've seen at least 3 articles
    cutoff_idx = None
    for i in range(body_start_idx, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            continue
        # Check for end markers
        if any(marker.lower() in stripped.lower() for marker in END_MARKERS):
            # Calculate evidence so far
            body_so_far = "\n".join(lines[body_start_idx:i])
            article_count_so_far = len(RE_ARTICLE.findall(body_so_far))
            body_chars_so_far = len(body_so_far)

            # Allow trimming if we have sufficient legal body evidence
            if (article_count_so_far >= 3 and body_chars_so_far >= 100) or \
               (article_count_so_far >= 3 and (body_chars_so_far >= 500 or i - body_start_idx >= 5)):
                cutoff_idx = i
                break

    if cutoff_idx is not None:
        lines = lines[:cutoff_idx]

    return "\n".join(lines)

def remove_safe_boilerplate(text: str) -> str:
    """Removes repeated non-legal boilerplate patterns conservatively.

    Preserves lines containing strong legal markers, structural numbering,
    and bare numbering to avoid damaging legal structure.
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

        # 4. Preserving bare numbering (formerly removed) to avoid damaging structure
        # during the cleaning phase before the legal parser.

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

    # Case-insensitive check for legal hierarchy
    summary.contains_part = bool(re.search(r"\bPhần\b", text, re.I))
    summary.contains_chapter = bool(re.search(r"\bChương\b", text, re.I))
    summary.contains_section = bool(re.search(r"\bMục\b", text, re.I))
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

        # Pipeline
        extracted_text, candidate_info = extract_legal_text_from_html(html_content)
        extracted_chars = len(extracted_text)

        text = trim_to_legal_body(extracted_text)
        text = remove_safe_boilerplate(text)
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

        # Optimized metadata fallback
        artifact = NormalizedArtifact(
            law_id=meta.get("law_id", law_id),
            law_name=meta.get("law_name") or meta.get("name") or "Unknown",
            source_url=meta.get("source_url") or meta.get("url") or "Unknown",
            source_domain=meta.get("source_domain") or "Unknown",
            source_type=meta.get("source_type") or "Unknown",
            raw_artifact_path=str(main_html_path),
            normalized_text=text,
            text_stats=stats,
            markers=markers,
            warnings=warnings,
            candidate_info=candidate_info
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
                "errors": [],
                "candidate_info": artifact.candidate_info
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
