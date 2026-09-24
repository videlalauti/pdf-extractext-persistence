"""Tests del persistence service con un repository fake en memoria."""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

import routes
from main import app

client = TestClient(app)


def _make_fake_repo():
    """Devuelve un MagicMock que imita a DocumentRepository con un dict interno _store."""
    repo = MagicMock()
    store = {}

    async def create(doc_id, content, checksum):
        document_id = doc_id or str(uuid.uuid4())
        doc = {"id": document_id, "content": content, "checksum": checksum}
        store[document_id] = doc
        return doc

    async def list_all():
        return list(store.values())

    async def get(document_id):
        if document_id not in store:
            raise HTTPException(status_code=404, detail="Document not found")
        return store[document_id]

    async def update(document_id, content=None, checksum=None):
        if document_id not in store:
            raise HTTPException(status_code=404, detail="Document not found")
        if content is not None:
            store[document_id]["content"] = content
        if checksum is not None:
            store[document_id]["checksum"] = checksum
        return store[document_id]

    async def delete(document_id):
        if document_id not in store:
            raise HTTPException(status_code=404, detail="Document not found")
        del store[document_id]
        return None

    repo.create = AsyncMock(side_effect=create)
    repo.list_all = AsyncMock(side_effect=list_all)
    repo.get = AsyncMock(side_effect=get)
    repo.update = AsyncMock(side_effect=update)
    repo.delete = AsyncMock(side_effect=delete)
    repo._store = store
    return repo


@pytest.fixture(autouse=True)
def fake_repository():
    routes.repository = _make_fake_repo()
    yield


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "persistence-service"


def test_create_and_get_document():
    response = client.post("/documents", json={"content": "extracted text", "checksum": "abc123"})
    assert response.status_code == 201
    created = response.json()
    assert created["content"] == "extracted text"

    get_response = client.get(f"/documents/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created["id"]


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