"""Excepciones de dominio de la persistencia; libres de dependencias HTTP."""


class PersistenceError(Exception):
    """Base de los errores de dominio de la capa de persistencia."""


class DocumentNotFoundError(PersistenceError):
    """El documento solicitado no existe en la colección."""

    def __init__(self, document_id: str | None = None) -> None:
        self.document_id = document_id
        super().__init__("Document not found")


class InvalidUpdateError(PersistenceError):
    """La actualización no contiene ningún campo modificable."""

    def __init__(self) -> None:
        super().__init__("No fields to update")


class DuplicateDocumentError(PersistenceError):
    """Ya existe un documento con el mismo checksum."""

    def __init__(self, checksum: str) -> None:
        self.checksum = checksum
        super().__init__(f"Document with checksum {checksum} already exists")
