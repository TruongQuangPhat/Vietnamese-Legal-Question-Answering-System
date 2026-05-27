from __future__ import annotations

import re
import unicodedata
import html
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
from bs4 import BeautifulSoup, NavigableString, Tag

# --- Constants ---

LEGAL_MARKERS_KEYWORDS = {"điều", "khoản", "điểm", "luật", "bộ luật", "văn bản hợp nhất", "quốc hội", "căn cứ"}
STRONG_LEGAL_MARKERS = {"Điều", "Chương", "Mục", "Phần", "Văn bản hợp nhất", "QUỐC HỘI", "Căn cứ", "Bộ luật", "Luật"}

PREFERRED_CONTENT_SELECTORS = [
    "#divContentDoc .content1",
    "#divContentDoc",
    ".cldivContentDocVn .content1",
    ".content1",
]
TEXT_BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TEXT_TAGS = {"script", "style", "noscript", "iframe", "button", "select", "input", "svg"}

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
RE_ARTICLE_1_LINE = re.compile(r"(?im)^\s*Điều\s+1\.")
RE_CLAUSE = re.compile(r"^\s*\d+\..+")  # require some text after "1."
RE_POINT = re.compile(r"^\s*[a-zđ]\).+", re.IGNORECASE)
EARLY_ARTICLE_1_WINDOW_CHARS = 3000
HEADER_LOOKBACK_LINES = 6

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
    max_article_number: int = 0
    has_article_1: bool = False
    has_article_2: bool = False
    article_sequence_score: float = 0.0

    max_article_number: int = 0
    has_article_1: bool = False
    has_article_2: bool = False
    article_sequence_score: float = 0.0


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
    for tag in soup.find_all(SKIP_TEXT_TAGS):
        tag.decompose()

    # 2. Try preferred TVPL selectors first
    for selector in PREFERRED_CONTENT_SELECTORS:
        elements = soup.select(selector)
        if not elements:
            continue

        # For TVPL, the legal body is often split across multiple blocks with the same class.
        # We concatenate them in DOM order to ensure completeness.
        # However, we only concatenate blocks that show legal evidence to avoid noise.
        valid_blocks = []
        for el in elements:
            block_text = extract_text_with_block_boundaries(el)
            if len(block_text) > 100 and (RE_ARTICLE.search(block_text) or any(m in block_text for m in STRONG_LEGAL_MARKERS)):
                valid_blocks.append(block_text)

        if not valid_blocks:
            continue

        full_text = "\n\n".join(valid_blocks)
        text_len = len(full_text)

        if text_len > 500: # Minimum threshold for a plausible legal body
            max_art = estimate_max_article_number(full_text)
            if max_art > 0:
                return full_text, {
                    "tag": elements[0].name,
                    "class": elements[0].get("class", []),
                    "id": elements[0].get("id", ""),
                    "selection_strategy": "preferred_tvpl_selector",
                    "selector": selector,
                    "article_count": len(RE_ARTICLE.findall(full_text)),
                    "max_article_number": max_art,
                    "has_article_1": has_article_number(full_text, 1),
                    "has_article_2": has_article_number(full_text, 2),
                    "article_sequence_score": compute_article_sequence_score(full_text),
                    "text_len": text_len,
                    "link_density": 0.0,
                    "avg_chars_per_article": text_len / (len(RE_ARTICLE.findall(full_text)) + 1),
                }

    # 3. Generic candidate scoring fallback
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
        text = extract_text_with_block_boundaries(candidate)
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
        final_text = extract_text_with_block_boundaries(best_candidate)
        final_dieu = len(RE_ARTICLE.findall(final_text))
        final_chapter = len(re.findall(r'Chương\s+[IVXLCDM]+', final_text, re.I))
        final_muc = final_text.count("Mục")
        link_count = len(best_candidate.find_all('a'))
        link_text_len = sum(len(a.get_text(strip=True)) for a in best_candidate.find_all('a') if a.get_text(strip=True))
        link_density = link_text_len / len(final_text) if final_text else 0

        return final_text, {
            "tag": best_candidate.name,
            "class": best_candidate.get("class", []),
            "id": best_candidate.get("id", ""),
            "selection_strategy": "fallback_scoring",
            "selector": None,
            "article_count": final_dieu,
            "max_article_number": estimate_max_article_number(final_text),
            "has_article_1": has_article_number(final_text, 1),
            "has_article_2": has_article_number(final_text, 2),
            "article_sequence_score": compute_article_sequence_score(final_text),
            "text_len": len(final_text),
            "link_density": 0.0, # Simplified for final
            "avg_chars_per_article": len(final_text) / (final_dieu + 1),
        }

    # Fallback: use body text
    body = soup.body
    if body:
        text = extract_text_with_block_boundaries(body)
        return text, {
            "tag": "body",
            "class": [],
            "id": "",
            "selection_strategy": "body_fallback",
            "selector": None,
            "article_count": 0,
            "max_article_number": 0,
            "has_article_1": False,
            "has_article_2": False,
            "article_sequence_score": 0.0,
            "text_len": len(text),
            "link_density": 0.0,
            "avg_chars_per_article": 0,
        }

    text = extract_text_with_block_boundaries(soup)
    return text, {
        "tag": "soup",
        "class": [],
        "id": "",
        "selection_strategy": "soup_fallback",
        "selector": None,
        "article_count": 0,
        "max_article_number": 0,
        "has_article_1": False,
        "has_article_2": False,
        "article_sequence_score": 0.0,
        "text_len": len(text),
        "link_density": 0.0,
        "avg_chars_per_article": 0,
    }

def extract_text_with_block_boundaries(node: Tag) -> str:
    """Extract visible text while preserving block, not inline, boundaries.

    Paragraph-like tags become separate lines. Inline formatting tags such as
    `span`, `font`, `b`, `i`, `u`, and `a` are joined as normal inline text so
    they do not create artificial word-fragment line breaks.
    """
    lines: List[str] = []

    def append_text(text: str) -> None:
        line = _normalize_extracted_line(text)
        if line:
            lines.append(line)

    def visit(current: Any) -> None:
        if isinstance(current, NavigableString):
            append_text(str(current))
            return
        if not isinstance(current, Tag):
            return
        if current.name in SKIP_TEXT_TAGS:
            return
        if current.name in TEXT_BLOCK_TAGS:
            append_text(current.get_text(separator="", strip=False))
            return

        for child in current.children:
            visit(child)

    visit(node)
    return "\n".join(lines)

def _normalize_extracted_line(text: str) -> str:
    """Normalize one extracted block line without altering legal structure."""
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([(])\s+", r"\1", text)
    return text

def trim_to_legal_body(text: str, candidate_info: Optional[Dict] = None) -> str:
    """Trims website chrome from the beginning and end of extracted text.

    Uses reliable legal headers to find the start of the actual legal document.
    Only applies end trimming after confirming substantial legal body content.

    Args:
        text: Extracted text from HTML.
        candidate_info: Info about how text was extracted (used to adjust trimming).

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
    # If we used a preferred selector, be extremely conservative with end trimming
    if candidate_info and candidate_info.get("selection_strategy") == "preferred_tvpl_selector":
        # Only trim if we have clearly passed the legal body (very aggressive markers)
        # Or just skip end trim entirely for preferred selectors to ensure completeness
        return text

    text = _trim_trailing_noise(text)

    return text

def _find_legal_body_start(text: str) -> int:
    """Finds the start position of the legal body using context-aware markers.

    Returns character index or len(text) if no reliable start found.
    """
    early_article_start = _find_start_from_early_article_1(text)
    if early_article_start is not None:
        return early_article_start

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

def _find_start_from_early_article_1(text: str) -> Optional[int]:
    """Find the legal body start when Article 1 appears near the beginning.

    Later amendment/source-law sections often contain strong `LUẬT...` markers.
    If Article 1 is already present early with enough following body evidence,
    prefer that earlier body and preserve nearby official title/header lines.
    """
    match = RE_ARTICLE_1_LINE.search(text)
    if not match or match.start() > EARLY_ARTICLE_1_WINDOW_CHARS:
        return None

    after_article_1 = text[match.start():]
    if not _has_sufficient_legal_evidence(after_article_1, min_articles=2, min_chars=100):
        return None

    return _find_nearby_official_header_start(text, match.start())

def _find_nearby_official_header_start(text: str, article_start: int) -> int:
    """Return the nearest official title/header start before Article 1."""
    line_spans = _line_spans(text)
    article_line_idx = next(
        (idx for idx, (start, end, _) in enumerate(line_spans) if start <= article_start < end),
        None,
    )
    if article_line_idx is None:
        return article_start

    lookback_start = max(0, article_line_idx - HEADER_LOOKBACK_LINES)
    for idx in range(article_line_idx - 1, lookback_start - 1, -1):
        line_text = line_spans[idx][2].strip()
        if not line_text:
            continue
        if _looks_like_amendment_source_note(line_text):
            continue

        header_lines = [
            span[2].strip()
            for span in line_spans[idx:article_line_idx]
            if span[2].strip()
        ]
        if _looks_like_official_header(header_lines):
            return line_spans[idx][0]

    return article_start

def _line_spans(text: str) -> List[Tuple[int, int, str]]:
    """Build `(start, end, line)` spans while preserving text offsets."""
    spans = []
    offset = 0
    for line in text.splitlines(keepends=True):
        start = offset
        end = offset + len(line)
        spans.append((start, end, line.rstrip("\r\n")))
        offset = end
    if text and not spans:
        spans.append((0, len(text), text))
    return spans

def _looks_like_official_header(lines: List[str]) -> bool:
    """Detect official legal title/header lines, including short split lines."""
    joined = " ".join(lines)
    joined_lower = joined.lower()
    if "căn cứ hiến pháp" in joined_lower and "quốc hội ban hành luật" in joined_lower:
        return True

    compact = re.sub(r"\s+", "", " ".join(lines)).upper()
    return compact.startswith((
        "LUẬT",
        "BỘLUẬT",
        "VĂNBẢNHỢPNHẤT",
        "HIẾNPHÁP",
        "PHÁPLỆNH",
        "NGHỊĐỊNH",
        "THÔNGTƯ",
        "QUỐCHỘI",
        "CHÍNHPHỦ",
    ))

def _looks_like_amendment_source_note(line: str) -> bool:
    """Detect pre-body source-law notes that should not anchor body start."""
    normalized = re.sub(r"\s+", " ", line).strip().lower()
    return normalized.startswith("luật số ") and "sửa đổi, bổ sung" in normalized

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

def extract_article_numbers(text: str) -> List[int]:
    """Extracts all article numbers found in the text."""
    # Matches "Điều 1", "Điều 12", etc.
    matches = RE_ARTICLE.findall(text)
    numbers = []
    for m in matches:
        # Extract digits from the match
        num_match = re.search(r"\d+", m)
        if num_match:
            numbers.append(int(num_match.group()))
    return numbers

def estimate_max_article_number(text: str) -> int:
    """Estimates the highest article number present in the text."""
    nums = extract_article_numbers(text)
    return max(nums) if nums else 0

def has_article_number(text: str, number: int) -> bool:
    """Checks if a specific article number is present."""
    nums = extract_article_numbers(text)
    return number in nums

def compute_article_sequence_score(text: str) -> float:
    """
    Computes a score based on how sequential and complete the articles are.
    Score = (unique articles found) / (max article number)
    """
    nums = sorted(list(set(extract_article_numbers(text))))
    if not nums:
        return 0.0
    max_num = nums[-1]
    if max_num == 0:
        return 0.0
    return len(nums) / max_num

def extract_article_numbers(text: str) -> List[int]:
    """Extracts all article numbers found in the text."""
    matches = RE_ARTICLE.findall(text)
    numbers = []
    for m in matches:
        num_match = re.search(r"\d+", m)
        if num_match:
            numbers.append(int(num_match.group()))
    return numbers

def estimate_max_article_number(text: str) -> int:
    """Estimates the highest article number present in the text."""
    nums = extract_article_numbers(text)
    return max(nums) if nums else 0

def has_article_number(text: str, number: int) -> bool:
    """Checks if a specific article number is present."""
    nums = extract_article_numbers(text)
    return number in nums

def compute_article_sequence_score(text: str) -> float:
    """
    Computes a score based on how sequential and complete the articles are.
    Score = (unique articles found) / (max article number)
    """
    nums = sorted(list(set(extract_article_numbers(text))))
    if not nums:
        return 0.0
    max_num = nums[-1]
    if max_num == 0:
        return 0.0
    return len(nums) / max_num

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

    normalized_lines = repair_line_fragments(normalized_lines)

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

def repair_line_fragments(lines: List[str]) -> List[str]:
    """Repair narrow, known-safe line fragments without flattening structure."""
    repaired = []
    idx = 0
    while idx < len(lines):
        current = lines[idx]
        next_line = lines[idx + 1] if idx + 1 < len(lines) else None

        if next_line is not None and _should_join_line_fragments(current, next_line):
            repaired.append(_join_line_fragments(current, next_line))
            idx += 2
            continue

        repaired.append(current)
        idx += 1

    return repaired

def _should_join_line_fragments(current: str, next_line: str) -> bool:
    """Return true only for safe legal heading or intra-word fragments."""
    if not current or not next_line:
        return False

    if current == "Điều" and re.match(r"^\d+\.", next_line):
        return True

    if " " in current or " " in next_line:
        return False

    return (current + next_line).lower() in {"điều", "mục", "việc"}

def _join_line_fragments(current: str, next_line: str) -> str:
    """Join a pair of fragments using the spacing needed by the fragment type."""
    if current == "Điều" and re.match(r"^\d+\.", next_line):
        return f"{current} {next_line}"
    return f"{current}{next_line}"

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
