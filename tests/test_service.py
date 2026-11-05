"""Casos de uso sin FastAPI ni Mongo (fake store)."""
import asyncio
from unittest.mock import AsyncMock

from persistence.service import DocumentService


def test_service_delegates_to_repository_and_preserves_data():
    repo = AsyncMock()
    expected = {"id": "doc-1", "content": "hola", "checksum": "sha"}
    repo.create.return_value = expected
    repo.get.return_value = expected
    service = DocumentService(repo)

    created = asyncio.run(service.create(None, "hola", "sha"))
    fetched = asyncio.run(service.get("doc-1"))

    assert created == fetched == expected
    repo.create.assert_awaited_once_with(None, "hola", "sha")
    repo.get.assert_awaited_once_with("doc-1")


def test_service_passes_through_domain_errors():
    from persistence.exceptions import DocumentNotFoundError

    repo = AsyncMock()
    repo.get.side_effect = DocumentNotFoundError("missing")
    service = DocumentService(repo)

    try:
        asyncio.run(service.get("missing"))
    except DocumentNotFoundError as error:
        assert error.document_id == "missing"
    else:
        raise AssertionError("DocumentNotFoundError esperado")
