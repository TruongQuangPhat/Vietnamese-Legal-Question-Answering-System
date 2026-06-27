"""Integration tests for the corpus processing workflow."""

from __future__ import annotations

import json
from pathlib import Path

from src.ingestion.cleaning_diagnostics import profile_raw_html
from src.services.cleaning_service import clean_raw_artifact


def test_corpus_processing_workflow_normalizes_tiny_raw_html(tmp_path: Path) -> None:
    """A tiny raw legal HTML fixture is cleaned into normalized UTF-8 output."""
    raw_dir = tmp_path / "raw" / "TINY_LAW" / "latest"
    output_dir = tmp_path / "interim"
    raw_dir.mkdir(parents=True)
    html_path = raw_dir / "main.html"
    metadata_path = raw_dir / "metadata.json"
    html_path.write_text(
        """
        <html>
          <body>
            <div id="divContentDoc">
              <div class="content1">
                <p>THƯ VIỆN PHÁP LUẬT</p>
                <p>Chương I</p>
                <p>QUY ĐỊNH CHUNG</p>
                <p>Điều&nbsp;1. Phạm vi điều chỉnh</p>
                <p>1. Khoản 1 quy định nội dung.</p>
                <p>a) điểm a quy định nội dung cụ thể.</p>
                <script>window.bad = true;</script>
                <p>Văn bản liên quan</p>
              </div>
            </div>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    metadata_path.write_text(
        json.dumps(
            {
                "law_id": "TINY_LAW",
                "law_name": "Luật Kiểm thử",
                "source_url": "https://thuvienphapluat.vn/tiny-law",
                "source_domain": "thuvienphapluat.vn",
                "source_type": "html",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    raw_profile = profile_raw_html("TINY_LAW", html_path)
    artifact, errors = clean_raw_artifact(
        (html_path, metadata_path),
        output_dir,
        min_text_length=1,
        write_txt=True,
    )

    assert errors == []
    assert raw_profile.has_divContentDoc is True
    assert artifact is not None
    assert artifact.normalized_text == (
        "Chương I\n"
        "QUY ĐỊNH CHUNG\n"
        "Điều 1. Phạm vi điều chỉnh\n"
        "1. Khoản 1 quy định nội dung.\n"
        "a) điểm a quy định nội dung cụ thể."
    )
    assert "THƯ VIỆN PHÁP LUẬT" not in artifact.normalized_text
    assert "Văn bản liên quan" not in artifact.normalized_text
    assert "window.bad" not in artifact.normalized_text
    assert "Điều 1" in artifact.normalized_text
    assert "Khoản 1" in artifact.normalized_text
    assert "điểm a" in artifact.normalized_text
    assert artifact.markers.contains_article is True
    assert artifact.markers.contains_clause_numbering is True
    assert artifact.markers.contains_point_labeling is True
    assert artifact.warnings == []

    normalized_path = output_dir / "TINY_LAW" / "normalized.json"
    cleaned_text_path = output_dir / "TINY_LAW" / "cleaned.txt"
    assert normalized_path.exists()
    assert cleaned_text_path.exists()
    assert normalized_path.is_relative_to(tmp_path)
    assert cleaned_text_path.is_relative_to(tmp_path)
    assert not (Path("data") / "raw" / "TINY_LAW").exists()
