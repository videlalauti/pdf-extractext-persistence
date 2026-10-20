"""Tests del persistence service con un repository fake en memoria."""

import io
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError
from shared.web.logging import RequestIdFormatter, RequestIdMiddleware, TimingMiddleware

import main
from persistence.exceptions import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    PersistenceError,
)
from routes import get_repository

client = TestClient(main.app)


class UnknownDomainError(PersistenceError):
    """Error de dominio que el traductor no conoce: no puede filtrarse como None."""


class FakeIndexCollection:
    """Colección mínima que solo registra los índices creados en el startup."""

    def __init__(self) -> None:
        self.indexes: list[tuple[str, bool]] = []

    async def create_index(self, field: str, unique: bool = False) -> str:
        self.indexes.append((field, unique))
        return f"{field}_{1 if unique else ''}"


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

    async def get_by_checksum(checksum):
        for doc in store.values():
            if doc["checksum"] == checksum:
                return doc
        raise DocumentNotFoundError()

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
    repo.get_by_checksum = AsyncMock(side_effect=get_by_checksum)
    repo.update = AsyncMock(side_effect=update)
    repo.delete = AsyncMock(side_effect=delete)
    repo._store = store
    return repo


@pytest.fixture
def mongo_collection() -> FakeIndexCollection:
    return FakeIndexCollection()


@pytest.fixture(autouse=True)
def fake_repository(monkeypatch, mongo_collection):
    """Sustituye el repositorio por la dependencia, sin tocar atributos de módulo."""
    repo = _make_fake_repo()
    main.app.dependency_overrides[get_repository] = lambda: repo
    monkeypatch.setattr(main.mongodb_connection, "connect", AsyncMock(return_value=None))
    monkeypatch.setattr(main.mongodb_connection, "disconnect", AsyncMock(return_value=None))
    monkeypatch.setattr(
        main.mongodb_connection,
        "get_database",
        lambda: {"documents": mongo_collection},
    )
    yield repo
    main.app.dependency_overrides.clear()


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


def test_get_document_by_checksum():
    created = client.post(
        "/documents", json={"content": "extracted text", "checksum": "abc123"}
    ).json()

    response = client.get("/documents/by-checksum/abc123")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_document_by_checksum_not_found():
    response = client.get("/documents/by-checksum/unknown-checksum")
    assert response.status_code == 404


def test_delete_document():
    created = client.post(
        "/documents", json={"content": "to be deleted", "checksum": "ccc"}
    ).json()

    delete_response = client.delete(f"/documents/{created['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/documents/{created['id']}")
    assert get_response.status_code == 404


def test_lifespan_creates_unique_checksum_index(mongo_collection):
    with TestClient(main.app):
        pass

    assert mongo_collection.indexes == [("checksum", True)]


def test_unknown_domain_error_becomes_500(fake_repository):
    fake_repository.get.side_effect = UnknownDomainError("algo nuevo")

    response = client.get("/documents/any-id")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal persistence error"


def test_non_domain_error_is_not_swallowed(fake_repository):
    """El raise final deja subir el error en vez de devolver None en silencio."""
    fake_repository.get.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        client.get("/documents/any-id")


def test_request_id_is_echoed_in_response_header():
    response = client.get("/health", headers={"X-Request-Id": "trace-123"})

    assert response.headers["X-Request-Id"] == "trace-123"


def test_cors_preflight_allows_configured_origin():
    response = client.options(
        "/documents",
        headers={
            "Origin": "http://localhost",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost"


def _middleware_classes() -> list[type]:
    """Clases del stack de la app, de afuera hacia adentro."""
    return [entry.cls for entry in main.app.user_middleware]


def test_timing_middleware_is_registered():
    assert TimingMiddleware in _middleware_classes()


def test_timing_middleware_runs_inside_request_id():
    """Request-id va afuera para que el ContextVar del request_id esté seteado
    cuando el timing emite su log (si no, el `request_id` saldría vacío)."""
    classes = _middleware_classes()
    assert classes.index(RequestIdMiddleware) < classes.index(TimingMiddleware)


def test_timing_log_carries_the_request_id():
    """Prueba de comportamiento: el log `request completed` hereda el request-id.

    El formatter resuelve el request-id del ContextVar al formatear, así que un
    handler temporal con el formatter real del servicio alcanza para verificar
    que TimingMiddleware corre por dentro de RequestIdMiddleware.
    """
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RequestIdFormatter("persistence-service"))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        client.get("/health", headers={"X-Request-Id": "trace-timing-42"})
    finally:
        root.removeHandler(handler)

    lines = [
        line
        for line in stream.getvalue().splitlines()
        if "request completed" in line
    ]
    assert len(lines) == 1, f"se esperaba un log de timing: {lines}"
    assert "trace-timing-42" in lines[0]


def test_timing_log_records_request_details(caplog):
    """El middleware loguea method, path, status_code y duration_ms por request."""
    with caplog.at_level(logging.INFO):
        response = client.get("/health")

    records = [r for r in caplog.records if r.getMessage() == "request completed"]
    assert len(records) == 1, f"se esperaba un log de timing: {records}"

    record = records[0]
    assert record.method == "GET"
    assert record.path == "/health"
    assert record.status_code == response.status_code
    assert isinstance(record.duration_ms, float)
    assert record.duration_ms >= 0
