from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import count

import httpx
import pytest
from fastapi import FastAPI

from src.api.app import create_app
from src.api.dependencies import get_conversation_service
from src.api.settings import AppSettings
from src.services.conversation_service import (
    ConversationService,
    InMemoryConversationRepository,
)

VALID_SESSION_SECRET = "unit-test-session-secret-with-enough-entropy"


@pytest.fixture
def conversation_app() -> FastAPI:
    timestamps = _timestamps()
    identifiers = (f"id-{value}" for value in count(1))
    service = ConversationService(
        InMemoryConversationRepository(),
        clock=lambda: next(timestamps),
        id_factory=lambda: next(identifiers),
    )
    app = create_app()

    async def get_test_conversation_service() -> ConversationService:
        return service

    app.dependency_overrides[get_conversation_service] = get_test_conversation_service
    return app


@pytest.mark.asyncio
async def test_create_conversation(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        response = await client.post(
            "/api/v1/conversations",
            json={"title": "  Hợp đồng lao động  "},
        )

    assert response.status_code == 201
    assert response.json() == {
        "id": "id-1",
        "title": "Hợp đồng lao động",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "message_count": 0,
    }


@pytest.mark.asyncio
async def test_create_conversation_uses_default_for_missing_or_blank_title(
    conversation_app: FastAPI,
) -> None:
    async with _client(conversation_app) as client:
        missing_response = await client.post("/api/v1/conversations", json={})
        blank_response = await client.post(
            "/api/v1/conversations",
            json={"title": "   "},
        )

    assert missing_response.status_code == 201
    assert missing_response.json()["title"] == "Cuộc trò chuyện mới"
    assert blank_response.status_code == 201
    assert blank_response.json()["title"] == "Cuộc trò chuyện mới"


@pytest.mark.asyncio
async def test_list_conversations_sorted_by_updated_at_descending(
    conversation_app: FastAPI,
) -> None:
    async with _client(conversation_app) as client:
        first = await _create(client, "First")
        second = await _create(client, "Second")
        await client.post(
            f"/api/v1/conversations/{first['id']}/messages",
            json={"role": "user", "content": "Newest activity"},
        )
        response = await client.get("/api/v1/conversations")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [first["id"], second["id"]]
    assert response.json()[0]["message_count"] == 1


@pytest.mark.asyncio
async def test_get_conversation_detail(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Detail")
        await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"role": "user", "content": "Câu hỏi"},
        )
        response = await client.get(
            f"/api/v1/conversations/{conversation['id']}",
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Detail"
    assert response.json()["messages"] == [
        {
            "id": "id-2",
            "role": "user",
            "content": "Câu hỏi",
            "created_at": "2025-01-01T00:00:01Z",
        }
    ]


@pytest.mark.asyncio
async def test_rename_conversation_updates_timestamp(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Old title")
        response = await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"title": "  New title  "},
        )

    assert response.status_code == 200
    assert response.json()["title"] == "New title"
    assert response.json()["updated_at"] > conversation["updated_at"]


@pytest.mark.asyncio
async def test_delete_conversation(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Delete me")
        delete_response = await client.delete(
            f"/api/v1/conversations/{conversation['id']}",
        )
        get_response = await client.get(
            f"/api/v1/conversations/{conversation['id']}",
        )

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert get_response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["user", "assistant"])
async def test_add_conversation_message(
    conversation_app: FastAPI,
    role: str,
) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Messages")
        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"role": role, "content": "  Nội dung tin nhắn  "},
        )
        list_response = await client.get("/api/v1/conversations")

    assert response.status_code == 201
    assert response.json()["role"] == role
    assert response.json()["content"] == "Nội dung tin nhắn"
    assert list_response.json()[0]["message_count"] == 1
    assert list_response.json()[0]["updated_at"] > conversation["updated_at"]


@pytest.mark.asyncio
async def test_unknown_conversation_returns_404(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        get_response = await client.get("/api/v1/conversations/unknown")
        patch_response = await client.patch(
            "/api/v1/conversations/unknown",
            json={"title": "Valid"},
        )
        delete_response = await client.delete("/api/v1/conversations/unknown")
        message_response = await client.post(
            "/api/v1/conversations/unknown/messages",
            json={"role": "user", "content": "Valid"},
        )

    assert {
        get_response.status_code,
        patch_response.status_code,
        delete_response.status_code,
        message_response.status_code,
    } == {404}


@pytest.mark.asyncio
async def test_empty_rename_title_is_rejected(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Original")
        response = await client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"title": "   "},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_empty_message_is_rejected(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Messages")
        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"role": "user", "content": "   "},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_message_role_is_rejected(conversation_app: FastAPI) -> None:
    async with _client(conversation_app) as client:
        conversation = await _create(client, "Messages")
        response = await client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json={"role": "system", "content": "Nội dung"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_auth_enabled_scopes_conversations_by_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _auth_conversation_app(monkeypatch)

    async with _client(app) as client:
        owner_a_create = await client.post(
            "/api/v1/conversations",
            json={"title": "Owner A"},
            headers={"X-Legal-QA-Session": "owner-a"},
        )
        owner_a_id = owner_a_create.json()["id"]
        owner_a_list = await client.get(
            "/api/v1/conversations",
            headers={"X-Legal-QA-Session": "owner-a"},
        )
        owner_b_list = await client.get(
            "/api/v1/conversations",
            headers={"X-Legal-QA-Session": "owner-b"},
        )

    assert owner_a_create.status_code == 201
    assert [item["id"] for item in owner_a_list.json()] == [owner_a_id]
    assert owner_b_list.status_code == 200
    assert owner_b_list.json() == []


@pytest.mark.asyncio
async def test_auth_enabled_blocks_cross_owner_conversation_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _auth_conversation_app(monkeypatch)

    async with _client(app) as client:
        owner_a_create = await client.post(
            "/api/v1/conversations",
            json={"title": "Owner A"},
            headers={"X-Legal-QA-Session": "owner-a"},
        )
        conversation_id = owner_a_create.json()["id"]
        read_response = await client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers={"X-Legal-QA-Session": "owner-b"},
        )
        patch_response = await client.patch(
            f"/api/v1/conversations/{conversation_id}",
            json={"title": "Owner B rename"},
            headers={"X-Legal-QA-Session": "owner-b"},
        )
        message_response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"role": "user", "content": "Cross-owner message"},
            headers={"X-Legal-QA-Session": "owner-b"},
        )
        delete_response = await client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers={"X-Legal-QA-Session": "owner-b"},
        )
        owner_a_read = await client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers={"X-Legal-QA-Session": "owner-a"},
        )

    assert {
        read_response.status_code,
        patch_response.status_code,
        message_response.status_code,
        delete_response.status_code,
    } == {404}
    assert owner_a_read.status_code == 200
    assert owner_a_read.json()["title"] == "Owner A"


@pytest.mark.asyncio
async def test_auth_enabled_rejects_missing_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _auth_conversation_app(monkeypatch)

    async with _client(app) as client:
        response = await client.get("/api/v1/conversations")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing session token."


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


def _auth_conversation_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    timestamps = _timestamps()
    identifiers = (f"id-{value}" for value in count(1))
    service = ConversationService(
        InMemoryConversationRepository(),
        clock=lambda: next(timestamps),
        id_factory=lambda: next(identifiers),
    )
    settings = AppSettings.from_env(
        {
            "LEGAL_QA_AUTH_ENABLED": "true",
            "LEGAL_QA_SESSION_SECRET": VALID_SESSION_SECRET,
        }
    )
    monkeypatch.setattr("src.api.session_identity.get_settings", lambda: settings)
    app = create_app()

    async def get_test_conversation_service() -> ConversationService:
        return service

    app.dependency_overrides[get_conversation_service] = get_test_conversation_service
    return app


async def _create(client: httpx.AsyncClient, title: str) -> dict[str, object]:
    response = await client.post("/api/v1/conversations", json={"title": title})
    assert response.status_code == 201
    return response.json()


def _timestamps() -> Iterator[datetime]:
    current = datetime(2025, 1, 1, tzinfo=UTC)
    while True:
        yield current
        current += timedelta(seconds=1)
