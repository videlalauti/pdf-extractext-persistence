"""Tests del persistence service con un repository fake en memoria."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

import main
import routes
from persistence.exceptions import DocumentNotFoundError, DuplicateDocumentError

client = TestClient(main.app)


def _make_fake_repo():
    """Devuelve un MagicMock que imita a DocumentRepository con un dict interno _store."""
    repo = MagicMock()
    store = {}

    async def create(doc_id, content, checksum):
        if any(doc["checksum"] == checksum for doc in store.values()):
            raise DuplicateDocumentError(checksum)
        document_id = doc_id or str(uuid.uuid4())
        doc = {"id": document_id, "content": content, "checksum": checksum}
        store[document_id] = doc
        return doc

    async def list_all():
        return list(store.values())

    async def get(document_id):
        if document_id not in store:
            raise DocumentNotFoundError(document_id)
        return store[document_id]

    async def update(document_id, content=None, checksum=None):
        if document_id not in store:
            raise DocumentNotFoundError(document_id)
        if content is not None:
            store[document_id]["content"] = content
        if checksum is not None:
            store[document_id]["checksum"] = checksum
        return store[document_id]

    async def delete(document_id):
        if document_id not in store:
            raise DocumentNotFoundError(document_id)
        del store[document_id]

    repo.create = AsyncMock(side_effect=create)
    repo.list_all = AsyncMock(side_effect=list_all)
    repo.get = AsyncMock(side_effect=get)
    repo.update = AsyncMock(side_effect=update)
    repo.delete = AsyncMock(side_effect=delete)
    repo._store = store
    return repo


@pytest.fixture(autouse=True)
def fake_repository(monkeypatch):
    routes.repository = _make_fake_repo()
    monkeypatch.setattr(main.mongodb_connection, "connect", AsyncMock(return_value=None))
    yield


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "persistence-service"


def test_health_check_unhealthy_when_mongo_down(monkeypatch):
    monkeypatch.setattr(
        main.mongodb_connection,
        "connect",
        AsyncMock(side_effect=ServerSelectionTimeoutError("mongo unreachable")),
    )

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}


def test_create_and_get_document():
    response = client.post("/documents", json={"content": "extracted text", "checksum": "abc123"})
    assert response.status_code == 201
    created = response.json()
    assert created["content"] == "extracted text"

    get_response = client.get(f"/documents/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]


def test_create_duplicate_checksum_returns_conflict():
    first = client.post("/documents", json={"content": "extracted text", "checksum": "abc123"})
    assert first.status_code == 201

    duplicate = client.post("/documents", json={"content": "other text", "checksum": "abc123"})
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Document with checksum abc123 already exists"


def test_list_documents():
    client.post("/documents", json={"content": "first", "checksum": "aaa"})
    client.post("/documents", json={"content": "second", "checksum": "bbb"})

    response = client.get("/documents")
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_document_not_found():
    response = client.get("/documents/nonexistent-id")
    assert response.status_code == 404


def test_delete_document():
    created = client.post(
        "/documents", json={"content": "to be deleted", "checksum": "ccc"}
    ).json()

    delete_response = client.delete(f"/documents/{created['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/documents/{created['id']}")
    assert get_response.status_code == 404