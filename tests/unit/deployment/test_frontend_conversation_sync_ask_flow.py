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
    sync_start = source.index("startBestEffortMessageSync(", ask_start)
    await_ask = source.index("const answer = await answerRequest;", sync_start)

    assert ask_start < sync_start < await_ask
    assert "conversation_id: backendConversationId" in source


def test_best_effort_sync_has_separate_error_boundary_from_ask() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    helper_start = source.index("function startBestEffortMessageSync(")
    helper_source = source[helper_start : source.index("function startNewChat()")]

    assert "queueMessageSync(" in helper_source
    assert '.catch {\n      warnBackendSyncFailure("message");\n    }' not in helper_source
    assert '} catch {\n      warnBackendSyncFailure("message");\n    }' in helper_source


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
    ask_await = submit_source.index("const answer = await answerRequest;")
    ask_catch = submit_source.index("} catch (error) {", ask_await)
    ask_error_boundary = submit_source[
        ask_catch : submit_source.index("function startBestEffortMessageSync(")
    ]

    assert "const errorMessage = toUserFacingError(error);" in ask_error_boundary
    assert 'status: "error"' in ask_error_boundary
    assert "warnBackendSyncFailure" not in ask_error_boundary
    assert "queueMessageSync(" not in ask_error_boundary


def test_ask_and_conversation_clients_share_base_url_joining_and_session_header() -> None:
    conversation_source = CONVERSATION_CLIENT.read_text(encoding="utf-8")
    ask_source = LEGAL_QA_CLIENT.read_text(encoding="utf-8")

    assert "joinApiPath(apiBaseUrl, path)" in conversation_source
    assert 'export const CONVERSATION_SESSION_HEADER = "X-Legal-QA-Session";' in conversation_source
    assert "export function getConversationSessionToken()" in conversation_source
    assert "getOptionalConversationSessionToken()" in ask_source
    assert "headers[CONVERSATION_SESSION_HEADER] = sessionToken;" in ask_source
    assert "joinApiPath(apiBaseUrl, LEGAL_QA_ASK_PATH)" in ask_source


def test_session_token_storage_failure_falls_back_or_is_omitted_without_blocking_fetch() -> None:
    conversation_source = CONVERSATION_CLIENT.read_text(encoding="utf-8")
    ask_source = LEGAL_QA_CLIENT.read_text(encoding="utf-8")

    assert "window.localStorage.getItem(SESSION_STORAGE_KEY)" in conversation_source
    assert "window.localStorage.setItem(SESSION_STORAGE_KEY, token)" in conversation_source
    assert (
        "} catch {\n    serverSessionToken ??= createSessionToken(window.crypto);"
        in conversation_source
    )
    assert (
        "export function getOptionalConversationSessionToken(): string | null"
        in conversation_source
    )
    assert "const sessionToken = getOptionalConversationSessionToken();" in ask_source
    assert "if (sessionToken)" in ask_source


def test_production_api_base_url_still_cannot_fall_back_to_localhost() -> None:
    source = API_CONFIG.read_text(encoding="utf-8")

    assert 'if (nodeEnv !== "production")' in source
    assert "return ACCEPTED_PRODUCTION_API_BASE_URL;" in source
    assert "https://vnlaw-backend-prod-phat.azurewebsites.net" in source
    assert "http://localhost:8000" not in source


def test_transient_assistant_errors_are_not_persisted_as_durable_history() -> None:
    source = (REPO_ROOT / "apps/frontend/src/components/legal-qa/chat-storage.ts").read_text(
        encoding="utf-8",
    )

    assert "stripTransientAssistantFailures" in source
    assert "conversations.map(stripTransientAssistantFailures)" in source
    assert 'message.role === "user" || message.status === "complete"' in source
