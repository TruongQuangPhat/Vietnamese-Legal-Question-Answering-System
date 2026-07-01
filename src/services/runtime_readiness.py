"""Safe runtime readiness checks for the Legal QA API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.indexing.qdrant_collection import build_qdrant_client
from src.services.legal_qa_workflow import LegalQAServiceMode

DEFAULT_READINESS_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ReadinessCheck:
    """One sanitized readiness check result."""

    name: str
    ready: bool
    detail: str


@dataclass(frozen=True)
class RuntimeReadiness:
    """Aggregate readiness result for the selected Legal QA service mode."""

    ready: bool
    service_mode: LegalQAServiceMode
    checks: tuple[ReadinessCheck, ...]


class QdrantReadinessProbeProtocol(Protocol):
    """Read-only Qdrant readiness probe contract."""

    async def check_collection(self, collection_name: str) -> None:
        """Confirm that collection metadata can be read."""
        ...


class QdrantCollectionReadinessProbe:
    """Check Qdrant collection metadata without retrieval or mutation."""

    def __init__(
        self,
        *,
        url: str,
        api_key: str | None = None,
        timeout_seconds: float = DEFAULT_READINESS_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize a lightweight Qdrant readiness probe.

        Args:
            url: Qdrant HTTP endpoint.
            api_key: Optional Qdrant credential.
            timeout_seconds: Short timeout for the metadata request.
        """
        self._url = url
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    async def check_collection(self, collection_name: str) -> None:
        """Read collection metadata and close the client.

        Args:
            collection_name: Existing legal chunk collection to inspect.

        Raises:
            Exception: Propagates client construction, connectivity, and
                collection lookup failures to the readiness service, which
                converts them to a sanitized unavailable result.

        Side effects:
            Performs one read-only Qdrant metadata request. It does not embed,
            retrieve, create, update, delete, or upsert data.
        """
        client = build_qdrant_client(
            url=self._url,
            timeout_seconds=self._timeout_seconds,
            api_key=self._api_key,
        )
        try:
            await client.get_collection(collection_name)
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                await close()


class RuntimeReadinessService:
    """Evaluate configuration and optional Qdrant readiness safely."""

    def __init__(
        self,
        *,
        service_mode: LegalQAServiceMode,
        configuration_issues: tuple[str, ...],
        qdrant_collection: str | None,
        qdrant_probe: QdrantReadinessProbeProtocol | None = None,
    ) -> None:
        """Initialize readiness evaluation with injected dependencies."""
        self._service_mode = service_mode
        self._configuration_issues = configuration_issues
        self._qdrant_collection = qdrant_collection
        self._qdrant_probe = qdrant_probe

    async def check(self) -> RuntimeReadiness:
        """Return readiness without loading models or calling an LLM.

        Returns:
            Sanitized configuration and Qdrant status. Fake mode is ready
            without external dependencies. Real mode requires valid
            configuration and a successful read-only collection metadata
            lookup.
        """
        if self._configuration_issues:
            return RuntimeReadiness(
                ready=False,
                service_mode=self._service_mode,
                checks=(
                    ReadinessCheck(
                        name="configuration",
                        ready=False,
                        detail=",".join(self._configuration_issues),
                    ),
                ),
            )

        configuration_check = ReadinessCheck(
            name="configuration",
            ready=True,
            detail="valid",
        )
        if self._service_mode == LegalQAServiceMode.FAKE:
            return RuntimeReadiness(
                ready=True,
                service_mode=self._service_mode,
                checks=(configuration_check,),
            )

        if self._qdrant_probe is None or self._qdrant_collection is None:
            qdrant_check = ReadinessCheck(
                name="qdrant",
                ready=False,
                detail="unavailable",
            )
        else:
            try:
                await self._qdrant_probe.check_collection(self._qdrant_collection)
            except Exception:
                qdrant_check = ReadinessCheck(
                    name="qdrant",
                    ready=False,
                    detail="unavailable",
                )
            else:
                qdrant_check = ReadinessCheck(
                    name="qdrant",
                    ready=True,
                    detail="collection_available",
                )

        return RuntimeReadiness(
            ready=qdrant_check.ready,
            service_mode=self._service_mode,
            checks=(configuration_check, qdrant_check),
        )
