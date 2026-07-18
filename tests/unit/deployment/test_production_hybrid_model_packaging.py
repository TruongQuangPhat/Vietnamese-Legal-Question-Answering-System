from __future__ import annotations

import ast
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_backend_dockerfile_packages_bge_m3_model_snapshot() -> None:
    dockerfile = (REPO_ROOT / "docker/backend/Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim AS embedding-model" in dockerfile
    assert "huggingface_hub==1.18.0" in dockerfile
    assert "snapshot_download(" in dockerfile
    assert "BAAI/bge-m3" in dockerfile
    assert "5617a9f61b028005a4858fdac845db406aefb181" in dockerfile
    assert (
        "COPY --from=embedding-model /models/embedding/bge-m3 /models/embedding/bge-m3"
        in dockerfile
    )
    assert "EMBEDDING_MODEL_PATH=/models/embedding/bge-m3" in dockerfile
    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile
    assert "HF_DATASETS_OFFLINE=1" in dockerfile


def test_production_deploy_preserves_hybrid_retrieval_and_model_path() -> None:
    workflow = (REPO_ROOT / ".github/workflows/deploy-production-container.yml").read_text(
        encoding="utf-8"
    )

    assert "EMBEDDING_MODEL_ID: BAAI/bge-m3" in workflow
    assert "EMBEDDING_MODEL_REVISION: 5617a9f61b028005a4858fdac845db406aefb181" in workflow
    assert "EMBEDDING_MODEL_PATH: /models/embedding/bge-m3" in workflow
    assert "--build-arg EMBEDDING_MODEL_PATH=" in workflow
    assert "Assert production backend image artifacts" in workflow
    assert "LEGAL_QA_RETRIEVAL_MODE=hybrid" in workflow
    assert "LEGAL_QA_RETRIEVAL_MODE=sparse" not in workflow
    assert "LEGAL_QA_RERANKING_ENABLED=false" in workflow
    assert "LEGAL_QA_MAX_TOP_K=5" in workflow
    assert "LEGAL_QA_EMBEDDING_MODEL_LOAD_TIMEOUT_SECONDS=120" in workflow
    assert "LEGAL_QA_WARMUP_TIMEOUT_SECONDS=180" in workflow
    assert "LEGAL_QA_WARMUP_ENDPOINT_ENABLED=true" in workflow
    assert 'EMBEDDING_MODEL_PATH="$EMBEDDING_MODEL_PATH"' in workflow
    assert "HF_HUB_OFFLINE=1" in workflow
    assert "TRANSFORMERS_OFFLINE=1" in workflow
    assert "HF_DATASETS_OFFLINE=1" in workflow


def test_production_ask_smoke_does_not_force_sparse_retrieval() -> None:
    workflow = (REPO_ROOT / ".github/workflows/production-ask-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "EXPECTED_RETRIEVAL_MODE: hybrid" in workflow
    assert "Expected production retrieval mode:" in workflow
    assert "LEGAL_QA_RETRIEVAL_MODE=sparse" not in workflow
    assert "/api/v1/legal-qa/ask" in workflow
    assert workflow.count("$base_url/api/v1/legal-qa/ask") == 1
    assert "validate_production_ask_smoke_response.py" in workflow
    assert "Ask smoke did not prepare a retrieval question." not in workflow


def test_production_ask_smoke_requires_packaged_model_warmup() -> None:
    workflow = (REPO_ROOT / ".github/workflows/production-ask-smoke.yml").read_text(
        encoding="utf-8"
    )
    validator = (
        REPO_ROOT / "scripts/deployment/validate_production_ask_smoke_response.py"
    ).read_text(encoding="utf-8")
    combined = workflow + "\n" + validator

    assert "Verify production embedding warmup" in workflow
    assert "--max-time 220" in workflow
    assert "validate_warmup_payload" in workflow
    assert workflow.count("$base_url/api/v1/legal-qa/warmup") == 2
    assert '"model_path_configured"' in combined
    assert '"model_path_exists"' in combined
    assert '"required_files_present"' in combined
    assert '"model_load_completed"' in combined
    assert '"encode_completed"' in combined
    assert '"cache_hit_after"' in combined
    assert "require_cache_hit_before=True" in workflow
    assert "WARMUP_MODEL_CACHE_KEY" in workflow
    assert "--expected-model-cache-key" in workflow


def test_production_ask_smoke_inline_python_imports_used_modules() -> None:
    workflow = (REPO_ROOT / ".github/workflows/production-ask-smoke.yml").read_text(
        encoding="utf-8"
    )

    for index, source in enumerate(_python_heredocs(workflow), start=1):
        tree = ast.parse(source)
        imported = _imported_names(tree)
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        missing = sorted((used & {"json", "os", "sys", "Path"}) - imported)
        assert missing == [], f"inline Python heredoc {index} missing imports: {missing}"


def test_sparse_mode_is_documented_as_emergency_degraded_only() -> None:
    docs = "\n".join(
        [
            (REPO_ROOT / "docs/api_deployment.md").read_text(encoding="utf-8"),
            (REPO_ROOT / "docs/ci_cd.md").read_text(encoding="utf-8"),
            (REPO_ROOT / "docs/runbooks/azure_deployment.md").read_text(encoding="utf-8"),
        ]
    )

    assert "hybrid is the canonical project pipeline" in docs
    assert "sparse is a degraded emergency mode only" in docs
    assert "Sparse mode must not be used to validate final production quality" in docs


def _python_heredocs(workflow: str) -> list[str]:
    scripts: list[str] = []
    lines = workflow.splitlines()
    index = 0
    while index < len(lines):
        if "python - <<'PY'" not in lines[index]:
            index += 1
            continue
        index += 1
        block: list[str] = []
        while index < len(lines) and lines[index].strip() != "PY":
            line = lines[index]
            block.append(line[10:] if line.startswith(" " * 10) else line)
            index += 1
        scripts.append(textwrap.dedent("\n".join(block)))
        index += 1
    return scripts


def _imported_names(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(
                alias.asname or alias.name.split(".", maxsplit=1)[0] for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.asname or alias.name for alias in node.names)
    return imported
