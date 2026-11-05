"""Capa de aplicación de documentos, desacoplada de FastAPI y del driver Mongo."""
from __future__ import annotations

from typing import Protocol


class DocumentStore(Protocol):
    async def create(self, doc_id: str | None, content: str, checksum: str) -> dict: ...
    async def list_all(self) -> list[dict]: ...
    async def get(self, document_id: str) -> dict: ...
    async def get_by_checksum(self, checksum: str) -> dict: ...
    async def update(self, document_id: str, content: str | None, checksum: str | None) -> dict: ...
    async def delete(self, document_id: str) -> None: ...


class DocumentService:
    """Casos de uso CRUD; el store inyectado es el puerto de persistencia."""

    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    async def create(self, doc_id: str | None, content: str, checksum: str) -> dict:
        return await self._store.create(doc_id, content, checksum)

    async def list_all(self) -> list[dict]:
        return await self._store.list_all()

    async def get(self, document_id: str) -> dict:
        return await self._store.get(document_id)

    async def get_by_checksum(self, checksum: str) -> dict:
        return await self._store.get_by_checksum(checksum)

    async def update(self, document_id: str, content: str | None, checksum: str | None) -> dict:
        return await self._store.update(document_id, content, checksum)

    async def delete(self, document_id: str) -> None:
        await self._store.delete(document_id)
