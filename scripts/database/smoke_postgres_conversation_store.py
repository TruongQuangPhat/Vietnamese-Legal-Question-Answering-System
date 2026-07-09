"""Smoke-test the PostgreSQL conversation store against an opted-in real DB."""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.api.schemas import (
    ConversationCreateRequest,
    ConversationMessageCreateRequest,
    ConversationMessageRole,
    ConversationUpdateRequest,
)
from src.services.conversation_service import ConversationNotFoundError, ConversationService
from src.services.postgres_conversation_repository import PostgresConversationRepository

SCHEMA_PATH = Path("scripts/database/postgres_conversation_store.sql")
ALLOW_DB_TESTS_ENV = "LEGAL_QA_ALLOW_DB_TESTS"
DATABASE_URL_ENV = "LEGAL_QA_DATABASE_URL"
TEST_PREFIX = "postgres_smoke"


def main() -> int:
    """Run a guarded PostgreSQL conversation lifecycle smoke test.

    Returns:
        Process exit code. Returns non-zero when configuration is missing, the
        schema is absent, or the lifecycle/cascade checks fail.

    Side effects:
        Connects to the PostgreSQL database selected by ``LEGAL_QA_DATABASE_URL``
        only when ``LEGAL_QA_ALLOW_DB_TESTS=1`` is present. Creates and deletes
        one temporary conversation and its messages. With ``--apply-schema``,
        applies the repository schema file before the lifecycle check.
    """
    args = _parse_args()
    if os.environ.get(ALLOW_DB_TESTS_ENV) != "1":
        print(
            f"Refusing to run: set {ALLOW_DB_TESTS_ENV}=1 to opt in to real DB tests.",
            file=sys.stderr,
        )
        return 2

    database_url = os.environ.get(DATABASE_URL_ENV, "").strip()
    if not database_url:
        print(f"Refusing to run: {DATABASE_URL_ENV} is required.", file=sys.stderr)
        return 2

    try:
        if args.apply_schema:
            _apply_schema(database_url)
        _run_smoke(database_url)
    except Exception as exc:
        print(f"PostgreSQL conversation smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("PostgreSQL conversation smoke passed using a redacted database URL.")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate PostgreSQL conversation storage with temporary records. "
            "Requires LEGAL_QA_ALLOW_DB_TESTS=1 and LEGAL_QA_DATABASE_URL."
        )
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help=(
            "Apply scripts/database/postgres_conversation_store.sql before running "
            "the lifecycle check."
        ),
    )
    return parser.parse_args()


def _apply_schema(database_url: str) -> None:
    if not SCHEMA_PATH.is_file():
        raise FileNotFoundError(f"missing schema file: {SCHEMA_PATH}")
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the postgres optional extra before DB validation.") from exc

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with psycopg.connect(database_url) as connection:
        connection.execute(schema_sql)


def _run_smoke(database_url: str) -> None:
    repository = PostgresConversationRepository(database_url)
    test_id = _test_id()
    service = ConversationService(
        repository,
        clock=lambda: datetime.now(UTC),
        id_factory=_id_factory(test_id),
    )

    conversation = service.create(ConversationCreateRequest(title=f"{test_id} original"))
    try:
        if conversation.title != f"{test_id} original":
            raise AssertionError("created conversation title did not round-trip")

        first = service.add_message(
            conversation.id,
            ConversationMessageCreateRequest(
                role=ConversationMessageRole.USER,
                content=f"{test_id} user message",
            ),
        )
        second = service.add_message(
            conversation.id,
            ConversationMessageCreateRequest(
                role=ConversationMessageRole.ASSISTANT,
                content=f"{test_id} assistant message",
            ),
        )
        detail = service.get(conversation.id)
        if [message.id for message in detail.messages] != [first.id, second.id]:
            raise AssertionError("messages did not round-trip in creation order")

        renamed = service.rename(
            conversation.id,
            ConversationUpdateRequest(title=f"{test_id} renamed"),
        )
        if renamed.title != f"{test_id} renamed":
            raise AssertionError("renamed conversation title did not round-trip")

        listed_ids = [item.id for item in service.list()]
        if conversation.id not in listed_ids:
            raise AssertionError("created conversation was absent from repository list")

        service.delete(conversation.id)
        try:
            service.get(conversation.id)
        except ConversationNotFoundError:
            pass
        else:
            raise AssertionError("deleted conversation remained readable")

        _assert_messages_deleted(database_url, conversation.id)
    finally:
        _cleanup(database_url, test_id)


def _assert_messages_deleted(database_url: str, conversation_id: str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError("Install the postgres optional extra before DB validation.") from exc

    with psycopg.connect(database_url) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM conversation_messages WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()[0]
    if count != 0:
        raise AssertionError("conversation delete did not cascade to messages")


def _cleanup(database_url: str, test_id: str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError:
        return

    with psycopg.connect(database_url) as connection:
        connection.execute(
            "DELETE FROM conversations WHERE id LIKE %s OR title LIKE %s",
            (f"{test_id}%", f"{test_id}%"),
        )


def _id_factory(test_id: str):
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"{test_id}_{counter}"

    return next_id


def _test_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{TEST_PREFIX}_{timestamp}_{secrets.token_hex(4)}"


if __name__ == "__main__":
    raise SystemExit(main())
