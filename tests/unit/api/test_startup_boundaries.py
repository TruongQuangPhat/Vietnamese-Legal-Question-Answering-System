from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

HEAVY_STARTUP_MODULES = (
    "src.indexing.embedding_model",
    "src.services.legal_qa_workflow",
    "src.retrieval.dense_retriever",
    "FlagEmbedding",
    "torch",
    "qdrant_client",
)


def test_app_import_does_not_load_retrieval_model_or_qdrant_modules() -> None:
    """FastAPI app import must keep liveness startup independent of RAG clients."""
    payload = _run_startup_probe(
        """
        import json
        import sys

        import src.api.app

        print(json.dumps({name: name in sys.modules for name in HEAVY_STARTUP_MODULES}))
        """
    )

    assert payload == dict.fromkeys(HEAVY_STARTUP_MODULES, False)


def test_health_request_does_not_load_retrieval_model_or_qdrant_modules() -> None:
    """The /health route must not initialize or import heavy retrieval dependencies."""
    payload = _run_startup_probe(
        """
        import asyncio
        import json
        import sys

        import httpx

        from src.api.app import app

        async def main() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
            ) as client:
                response = await client.get("/health")
            print(
                json.dumps(
                    {
                        "status_code": response.status_code,
                        "modules": {
                            name: name in sys.modules for name in HEAVY_STARTUP_MODULES
                        },
                    }
                )
            )

        asyncio.run(main())
        """
    )

    assert payload["status_code"] == 200
    assert payload["modules"] == dict.fromkeys(HEAVY_STARTUP_MODULES, False)


def _run_startup_probe(source: str) -> dict[str, object]:
    probe = (
        "from __future__ import annotations\n"
        f"HEAVY_STARTUP_MODULES = {HEAVY_STARTUP_MODULES!r}\n" + textwrap.dedent(source)
    )
    env = {
        **os.environ,
        "LEGAL_QA_SERVICE_MODE": "fake",
        "LEGAL_QA_EMBEDDING_WARMUP_ENABLED": "false",
        "LEGAL_QA_ALLOW_REAL_TESTS": "0",
        "LEGAL_QA_ALLOW_DB_TESTS": "0",
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "QDRANT_API_KEY": "",
        "LEGAL_QA_QDRANT_API_KEY": "",
        "LEGAL_QA_DATABASE_URL": "",
        "LEGAL_QA_SESSION_SECRET": "",
        "HF_TOKEN": "",
    }
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])
