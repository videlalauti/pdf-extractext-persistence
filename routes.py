"""Persistence service: endpoints HTTP CRUD delegando en DocumentRepository."""

from collections.abc import Awaitable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from persistence.exceptions import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    InvalidUpdateError,
)
from persistence.mongodb_connection import MongoDBConnection
from persistence.repository import DocumentRepository

router = APIRouter()

T = TypeVar("T")


class DocumentCreate(BaseModel):
    id: str | None = None
    content: str
    checksum: str


class DocumentUpdate(BaseModel):
    content: str | None = None
    checksum: str | None = None


class DocumentResponse(BaseModel):
    id: str
    content: str
    checksum: str


repository = DocumentRepository(MongoDBConnection())


async def _translate_domain_errors(operation: Awaitable[T]) -> T:
    """Traduce las excepciones de dominio de la persistencia a HTTPException."""
    try:
        return await operation
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(error)
        ) from error
    except InvalidUpdateError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from error
    except DuplicateDocumentError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(error)
        ) from error


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(doc: DocumentCreate) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(repository.create(doc.id, doc.content, doc.checksum))
    )


@router.get("/documents", response_model=list[DocumentResponse])
async def get_documents() -> list[DocumentResponse]:
    return [
        DocumentResponse(**document)
        for document in await _translate_domain_errors(repository.list_all())
    ]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(repository.get(document_id))
    )


@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(document_id: str, doc_update: DocumentUpdate) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(
            repository.update(document_id, doc_update.content, doc_update.checksum)
        )
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str) -> None:
    await _translate_domain_errors(repository.delete(document_id))
