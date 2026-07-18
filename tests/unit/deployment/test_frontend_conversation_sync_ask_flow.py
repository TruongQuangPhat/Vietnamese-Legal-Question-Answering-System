from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE = REPO_ROOT / "apps/frontend/src/components/legal-qa/legal-qa-workspace.tsx"
CONVERSATION_CLIENT = REPO_ROOT / "apps/frontend/src/lib/conversation-client.ts"
LEGAL_QA_CLIENT = REPO_ROOT / "apps/frontend/src/lib/legal-qa-client.ts"
API_CONFIG = REPO_ROOT / "apps/frontend/src/lib/api-config.ts"


def test_conversation_create_sync_failure_warning_source_is_sanitized() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")

    assert "Conversation backend sync failed during ${operation}." in source
    assert 'warnBackendSyncFailure("create")' in source
    assert "console.warn(`Conversation backend sync failed during ${operation}.`);" in source


def test_submit_starts_ask_before_best_effort_conversation_sync() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    submit_start = source.index("async function submitQuestion()")
    ask_start = source.index("const answerRequest = askLegalQuestion", submit_start)
    sync_start = source.index("queueMessageSync(", ask_start)
    await_ask = source.index("const answer = await answerRequest;", sync_start)

    assert ask_start < sync_start < await_ask
    assert "conversation_id: backendConversationId" in source


def test_conversation_sync_queue_catches_failures_without_blocking_future_syncs() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    queue_start = source.index("function queueMessageSync(")
    queue_source = source[queue_start : source.index("async function syncMessageToBackend")]

    assert "previousSync" in queue_source
    assert '.catch(() => {\n        warnBackendSyncFailure("message");\n      })' in queue_source
    assert "void nextSync.finally(() => {" in queue_source


def test_user_facing_error_is_only_set_from_ask_failure_path() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    submit_start = source.index("async function submitQuestion()")
    submit_source = source[submit_start : source.index("function startNewChat()")]

    assert "const errorMessage = toUserFacingError(error);" in submit_source
    assert 'status: "error"' in submit_source
    assert (
        "warnBackendSyncFailure"
        not in submit_source[
            submit_source.index("} catch (error) {") : submit_source.index(
                "function startNewChat()",
            )
            if "function startNewChat()" in submit_source
            else len(submit_source)
        ]
    )


def test_ask_and_conversation_clients_share_base_url_joining_and_session_header() -> None:
    conversation_source = CONVERSATION_CLIENT.read_text(encoding="utf-8")
    ask_source = LEGAL_QA_CLIENT.read_text(encoding="utf-8")

    assert "joinApiPath(apiBaseUrl, path)" in conversation_source
    assert 'export const CONVERSATION_SESSION_HEADER = "X-Legal-QA-Session";' in conversation_source
    assert "export function getConversationSessionToken()" in conversation_source
    assert "[CONVERSATION_SESSION_HEADER]: getConversationSessionToken()" in ask_source
    assert "joinApiPath(apiBaseUrl, LEGAL_QA_ASK_PATH)" in ask_source


def test_session_token_storage_failure_falls_back_without_blocking_fetch() -> None:
    conversation_source = CONVERSATION_CLIENT.read_text(encoding="utf-8")

    assert "window.localStorage.getItem(SESSION_STORAGE_KEY)" in conversation_source
    assert "window.localStorage.setItem(SESSION_STORAGE_KEY, token)" in conversation_source
    assert (
        "} catch {\n    serverSessionToken ??= createSessionToken(window.crypto);"
        in conversation_source
    )


def test_production_api_base_url_still_cannot_fall_back_to_localhost() -> None:
    source = API_CONFIG.read_text(encoding="utf-8")

    assert "NEXT_PUBLIC_API_BASE_URL must be set for production frontend builds." in source
    assert 'if (nodeEnv !== "production")' in source
    assert "http://localhost:8000" not in source
