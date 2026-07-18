from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
API_CONFIG = REPO_ROOT / "apps/frontend/src/lib/api-config.ts"
LEGAL_QA_CLIENT = REPO_ROOT / "apps/frontend/src/lib/legal-qa-client.ts"
FRONTEND_README = REPO_ROOT / "apps/frontend/README.md"


def test_frontend_api_config_uses_accepted_azure_when_production_env_is_missing() -> None:
    source = API_CONFIG.read_text(encoding="utf-8")

    assert "const trimmedValue = configuredValue?.trim();" in source
    assert "if (trimmedValue)" in source
    assert "return normalizeApiBaseUrl(trimmedValue);" in source
    assert 'nodeEnv !== "production"' in source
    assert "ACCEPTED_PRODUCTION_API_BASE_URL" in source
    assert "https://vnlaw-backend-prod-phat.azurewebsites.net" in source
    assert "process.env.NEXT_PUBLIC_API_BASE_URL ??" not in source


def test_frontend_api_config_allows_localhost_only_outside_production() -> None:
    source = API_CONFIG.read_text(encoding="utf-8")

    assert "const LOCAL_DEV_HOST = String.fromCharCode(" in source
    assert "const LOCAL_DEV_API_BASE_URL = `http://${LOCAL_DEV_HOST}:8000`;" in source
    assert 'if (nodeEnv !== "production")' in source
    assert "return LOCAL_DEV_API_BASE_URL;" in source
    assert "http://localhost:8000" not in source


def test_frontend_api_config_normalizes_base_url_and_joins_paths() -> None:
    source = API_CONFIG.read_text(encoding="utf-8")
    client_source = LEGAL_QA_CLIENT.read_text(encoding="utf-8")

    assert "value.trim()" in source
    assert 'replace(/\\/+$/, "")' in source
    assert "export function joinApiPath" in source
    assert 'path.startsWith("/")' in source
    assert "joinApiPath(apiBaseUrl, LEGAL_QA_ASK_PATH)" in client_source


def test_frontend_readme_documents_azure_production_network_target() -> None:
    readme = FRONTEND_README.read_text(encoding="utf-8")

    assert "NEXT_PUBLIC_API_BASE_URL=https://vnlaw-backend-prod-phat.azurewebsites.net" in readme
    assert "http://localhost:8000/api/v1/legal-qa/ask" in readme
    assert "https://vnlaw-backend-prod-phat.azurewebsites.net/api/v1/legal-qa/ask" in readme
    assert "If the production bundle is missing this environment variable" in readme
