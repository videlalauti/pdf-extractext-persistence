"""Tests unitarios de DocumentRepository contra una colección Motor falsa en memoria."""

from dataclasses import dataclass

import pytest

from persistence.exceptions import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    InvalidUpdateError,
)
from persistence.repository import DocumentRepository


@dataclass
class _FakeUpdateResult:
    matched_count: int
    modified_count: int = 0


@dataclass
class _FakeDeleteResult:
    deleted_count: int


class FakeCollection:
    """Implementa el subconjunto de AsyncIOMotorCollection que usa DocumentRepository."""

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}

    async def insert_one(self, document: dict) -> None:
        self.docs[str(document["_id"])] = dict(document)

    async def find_one(self, query: dict) -> dict | None:
        for document in self.docs.values():
            if all(document.get(key) == value for key, value in query.items()):
                return dict(document)
        return None

    async def find(self, query: dict | None = None):
        for document in list(self.docs.values()):
            yield dict(document)

    async def update_one(self, query: dict, update: dict) -> _FakeUpdateResult:
        document = self.docs.get(str(query["_id"]))
        if not document:
            return _FakeUpdateResult(matched_count=0)
        document.update(update["$set"])
        return _FakeUpdateResult(matched_count=1, modified_count=1)

    async def delete_one(self, query: dict) -> _FakeDeleteResult:
        existed = self.docs.pop(str(query["_id"]), None) is not None
        return _FakeDeleteResult(deleted_count=1 if existed else 0)


class FakeConnection:
    """Conexión que devuelve siempre la misma FakeCollection, como el singleton real."""

    def __init__(self, collection: FakeCollection) -> None:
        self._collection = collection

    def get_database(self) -> dict:
        return {DocumentRepository.COLLECTION_NAME: self._collection}


@pytest.fixture
def collection() -> FakeCollection:
    return FakeCollection()


@pytest.fixture
def repository(collection: FakeCollection) -> DocumentRepository:
    return DocumentRepository(FakeConnection(collection))


@pytest.mark.anyio
async def test_create_generates_id_when_not_provided(repository, collection):
    created = await repository.create(None, "extracted text", "abc123")

    assert created["id"] in collection.docs
    assert created["content"] == "extracted text"
    assert created["checksum"] == "abc123"


@pytest.mark.anyio
async def test_create_uses_provided_id(repository):
    created = await repository.create("custom-id", "text", "abc123")

    assert created["id"] == "custom-id"


@pytest.mark.anyio
async def test_create_duplicate_checksum_raises_duplicate(repository, collection):
    await repository.create("doc-1", "first", "abc123")

    with pytest.raises(DuplicateDocumentError):
        await repository.create("doc-2", "second", "abc123")

    assert list(collection.docs) == ["doc-1"]


@pytest.mark.anyio
async def test_create_allows_different_checksum(repository):
    await repository.create("doc-1", "first", "aaa")
    await repository.create("doc-2", "second", "bbb")

    assert await repository.list_all() == [
        {"id": "doc-1", "content": "first", "checksum": "aaa"},
        {"id": "doc-2", "content": "second", "checksum": "bbb"},
    ]


@pytest.mark.anyio
async def test_get_existing_document(repository):
    await repository.create("doc-1", "hello", "aaa")

    assert await repository.get("doc-1") == {
        "id": "doc-1",
        "content": "hello",
        "checksum": "aaa",
    }


@pytest.mark.anyio
async def test_get_missing_document_raises_not_found(repository):
    with pytest.raises(DocumentNotFoundError):
        await repository.get("nonexistent-id")


@pytest.mark.anyio
async def test_list_all_returns_every_document(repository):
    await repository.create("doc-1", "first", "aaa")
    await repository.create("doc-2", "second", "bbb")

    assert await repository.list_all() == [
        {"id": "doc-1", "content": "first", "checksum": "aaa"},
        {"id": "doc-2", "content": "second", "checksum": "bbb"},
    ]


@pytest.mark.anyio
async def test_list_all_on_empty_collection(repository):
    assert await repository.list_all() == []


@pytest.mark.anyio
async def test_update_partial_keeps_other_fields(repository):
    await repository.create("doc-1", "hello", "aaa")

    updated = await repository.update("doc-1", "bye", None)

    assert updated == {"id": "doc-1", "content": "bye", "checksum": "aaa"}


@pytest.mark.anyio
async def test_update_missing_document_raises_not_found(repository):
    with pytest.raises(DocumentNotFoundError):
        await repository.update("nonexistent-id", "bye", None)


@pytest.mark.anyio
async def test_update_without_fields_raises_invalid_update(repository):
    with pytest.raises(InvalidUpdateError):
        await repository.update("doc-1", None, None)


@pytest.mark.anyio
async def test_delete_removes_document(repository):
    await repository.create("doc-1", "hello", "aaa")

    assert await repository.delete("doc-1") is None
    assert await repository.list_all() == []


@pytest.mark.anyio
async def test_delete_missing_document_raises_not_found(repository):
    with pytest.raises(DocumentNotFoundError):
        await repository.delete("nonexistent-id")
