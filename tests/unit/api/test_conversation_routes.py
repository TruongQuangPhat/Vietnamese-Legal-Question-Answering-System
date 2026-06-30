from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from itertools import count

import httpx
import pytest
from fastapi import FastAPI

from src.api.app import create_app
from src.api.dependencies import get_conversation_service
from src.services.conversation_service import (
    ConversationService,
    InMemoryConversationRepository,
)


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


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    )


async def _create(client: httpx.AsyncClient, title: str) -> dict[str, object]:
    response = await client.post("/api/v1/conversations", json={"title": title})
    assert response.status_code == 201
    return response.json()


def _timestamps() -> Iterator[datetime]:
    current = datetime(2025, 1, 1, tzinfo=UTC)
    while True:
        yield current
        current += timedelta(seconds=1)
