"""Tests unitarios de DocumentRepository contra una colección Motor falsa en memoria."""

import asyncio
from dataclasses import dataclass

import pytest
from pymongo.errors import DuplicateKeyError

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
    """Implementa el subconjunto de AsyncIOMotorCollection que usa DocumentRepository.

    `insert_one` respeta el índice único en checksum *solo* si `create_index`
    se llamó antes, igual que en Mongo: sin el índice el fake deja pasar
    duplicados y el repositorio se apoya en su `find_one`.
    """

    def __init__(self) -> None:
        self.docs: dict[str, dict] = {}
        self.indexes: dict[str, bool] = {}

    async def create_index(self, field: str, unique: bool = False) -> str:
        self.indexes[field] = unique
        return f"{field}_{1 if unique else ''}"

    async def insert_one(self, document: dict) -> None:
        if self.indexes.get("checksum") and any(
            doc["checksum"] == document["checksum"] for doc in self.docs.values()
        ):
            raise DuplicateKeyError(f"checksum {document['checksum']} ya indexado")
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


class RacingCollection(FakeCollection):
    """Colección donde el documento competidor ya está pero `find_one` no lo ve.

    Es la ventana real entre el `find_one` y el `insert_one` de dos requests
    concurrentes con el mismo checksum: sin índice único, ambos insertan.
    """

    async def find_one(self, query: dict) -> dict | None:
        if "checksum" in query:
            return None
        return await super().find_one(query)


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
async def test_ensure_indexes_creates_unique_index_on_checksum(repository, collection):
    await repository.ensure_indexes()

    assert collection.indexes == {"checksum": True}


@pytest.mark.anyio
async def test_ensure_indexes_is_idempotent(repository, collection):
    await repository.ensure_indexes()
    await repository.ensure_indexes()

    assert collection.indexes == {"checksum": True}


@pytest.mark.anyio
async def test_create_translates_duplicate_key_error_on_checksum_race():
    """La carrera entre find_one e insert_one la corta el índice único."""
    collection = RacingCollection()
    collection.docs["competidor"] = {
        "_id": "competidor",
        "content": "otro texto",
        "checksum": "abc123",
    }
    repository = DocumentRepository(FakeConnection(collection))
    await repository.ensure_indexes()

    with pytest.raises(DuplicateDocumentError):
        await repository.create("doc-1", "primero", "abc123")

    assert list(collection.docs) == ["competidor"]


@pytest.mark.anyio
async def test_create_allows_duplicate_checksum_without_unique_index(repository, collection):
    """Sin el índice creado, la garantía es solo el find_one del repositorio."""
    await repository.create("doc-1", "first", "abc123")
    await repository.ensure_indexes()

    created = await repository.create("doc-2", "second", "def456")

    assert created["checksum"] == "def456"
    assert sorted(collection.docs) == ["doc-1", "doc-2"]


@pytest.mark.anyio
async def test_concurrent_create_with_same_checksum_keeps_one_document():
    """Dos requests concurrentes con el mismo checksum: una entra, la otra es duplicado.

    Sin el índice único las dos pasarían el `find_one` y quedarían dos
    documentos con el mismo checksum, que es exactamente lo que el dedup
    tiene que impedir.
    """
    collection = RacingCollection()
    repository = DocumentRepository(FakeConnection(collection))
    await repository.ensure_indexes()

    results = await asyncio.gather(
        repository.create("doc-1", "primero", "abc123"),
        repository.create("doc-2", "segundo", "abc123"),
        return_exceptions=True,
    )

    created = [item for item in results if isinstance(item, dict)]
    duplicates = [item for item in results if isinstance(item, DuplicateDocumentError)]

    assert len(created) == 1
    assert len(duplicates) == 1
    assert list(collection.docs) == [created[0]["id"]]


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
async def test_get_by_checksum_returns_document(repository):
    await repository.create("doc-1", "hello", "abc123")
    await repository.create("doc-2", "bye", "def456")

    assert await repository.get_by_checksum("def456") == {
        "id": "doc-2",
        "content": "bye",
        "checksum": "def456",
    }


@pytest.mark.anyio
async def test_get_by_checksum_missing_raises_not_found(repository):
    with pytest.raises(DocumentNotFoundError):
        await repository.get_by_checksum("unknown-checksum")


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
    with pytest.raises(InvalidUpdateError) as raised:
        await repository.update("doc-1", None, None)

    assert str(raised.value) == "No fields to update"


@pytest.mark.anyio
async def test_delete_removes_document(repository):
    await repository.create("doc-1", "hello", "aaa")

    assert await repository.delete("doc-1") is None
    assert await repository.list_all() == []


@pytest.mark.anyio
async def test_delete_missing_document_raises_not_found(repository):
    with pytest.raises(DocumentNotFoundError):
        await repository.delete("nonexistent-id")
