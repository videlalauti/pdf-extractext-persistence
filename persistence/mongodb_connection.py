"""Conexión a MongoDB: configuración vía pydantic-settings y ciclo de vida."""

from typing import Optional, Self
from urllib.parse import quote

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic_settings import BaseSettings


class MongoSettings(BaseSettings):
    mongodb_root_username: str = "admin"
    mongodb_root_password: str = "changeme"
    mongodb_host: str = "mongo"
    mongodb_port: str = "27017"
    mongodb_database_name: str = "pdf_extractext"
    mongodb_auth_source: str = "admin"

    def build_url(self) -> str:
        # La credencial va percent-encoded: un password con @, : o / cortaría
        # la URL en el userinfo y la conexión apuntaría a otro host o usuario.
        user = quote(self.mongodb_root_username, safe="")
        password = quote(self.mongodb_root_password, safe="")
        host = self.mongodb_host
        port = self.mongodb_port
        db_name = self.mongodb_database_name
        auth_source = self.mongodb_auth_source
        return f"mongodb://{user}:{password}@{host}:{port}/{db_name}?authSource={auth_source}"


class MongoDBConnection:
    """Singleton: un único cliente Motor compartido por todo el proceso."""

    _instance: Optional["MongoDBConnection"] = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_client"):
            return
        settings = MongoSettings()
        self._client = AsyncIOMotorClient(
            settings.build_url(),
            maxPoolSize=50,
            minPoolSize=10,
            maxIdleTimeMS=45000,
            serverSelectionTimeoutMS=5000,
        )
        self._database = self._client[settings.mongodb_database_name]

    async def connect(self) -> None:
        await self._client.admin.command("ping")

    async def disconnect(self) -> None:
        self._client.close()

    def get_database(self) -> AsyncIOMotorDatabase:
        return self._database


mongodb_connection = MongoDBConnection()
