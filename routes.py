"""Capa HTTP CRUD: delega casos de uso a DocumentService."""

import logging
from collections.abc import Awaitable
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from persistence.exceptions import (
    DocumentNotFoundError,
    DuplicateDocumentError,
    InvalidUpdateError,
    PersistenceError,
)
from persistence.mongodb_connection import mongodb_connection
from persistence.repository import DocumentRepository
from persistence.service import DocumentService

logger = logging.getLogger(__name__)

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


def get_repository() -> DocumentRepository:
    """Proveedor del repositorio para la inyección de dependencias de FastAPI.

    El router depende de este contrato, no de la implementación: los tests
    lo sustituyen con `app.dependency_overrides` en vez de parchear un atributo
    de módulo. `MongoDBConnection` es un singleton y resolver la colección no
    hace I/O, así que un repository por request no cuesta nada.
    """
    return DocumentRepository(mongodb_connection)


RepositoryDependency = Annotated[DocumentRepository, Depends(get_repository)]


def get_document_service(repository: RepositoryDependency) -> DocumentService:
    """Inyecta los casos de uso, manteniendo el repositorio sustituible en tests."""
    return DocumentService(repository)


DocumentServiceDependency = Annotated[DocumentService, Depends(get_document_service)]


async def _translate_domain_errors(operation: Awaitable[T]) -> T:
    """Traduce las excepciones de dominio de la persistencia a HTTPException.

    Toda salida es un valor o una excepción: nunca `None`, porque un `None`
    silencioso se convierte en un `TypeError` lejos de la causa real.
    """
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
    except PersistenceError as error:
        # Error de dominio sin mapeo: es un bug, no un resultado de negocio.
        logger.exception("Error de persistencia sin mapeo HTTP: %s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal persistence error",
        ) from error
    except Exception as error:
        # Raise final: lo que no es de dominio se loguea con traceback y sube,
        # en vez de convertirse en un None silencioso.
        logger.exception("Fallo no mapeado en la capa HTTP: %s", type(error).__name__)
        raise


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    doc: DocumentCreate,
    service: DocumentServiceDependency,
) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(service.create(doc.id, doc.content, doc.checksum))
    )


@router.get("/documents", response_model=list[DocumentResponse])
async def get_documents(
    service: DocumentServiceDependency,
) -> list[DocumentResponse]:
    return [
        DocumentResponse(**document)
        for document in await _translate_domain_errors(service.list_all())
    ]


@router.get("/documents/by-checksum/{checksum}", response_model=DocumentResponse)
async def get_document_by_checksum(
    checksum: str,
    service: DocumentServiceDependency,
) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(service.get_by_checksum(checksum))
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    service: DocumentServiceDependency,
) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(service.get(document_id))
    )


@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    doc_update: DocumentUpdate,
    service: DocumentServiceDependency,
) -> DocumentResponse:
    return DocumentResponse(
        **await _translate_domain_errors(
            service.update(document_id, doc_update.content, doc_update.checksum)
        )
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    service: DocumentServiceDependency,
) -> None:
    await _translate_domain_errors(service.delete(document_id))
