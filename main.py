"""Persistence service FastAPI application: bootstrap y ciclo de vida de MongoDB."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from shared.web.cors import add_cors
from shared.web.logging import RequestIdMiddleware, setup_logging

from persistence.mongodb_connection import mongodb_connection
from routes import get_repository, router

SERVICE_NAME = "persistence-service"

setup_logging(SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongodb_connection.connect()
    await get_repository().ensure_indexes()
    yield
    await mongodb_connection.disconnect()


app = FastAPI(title="Document Persistence Service", version="1.0.0", lifespan=lifespan)

add_cors(app)
app.add_middleware(RequestIdMiddleware)


@app.get("/health")
async def health():
    try:
        await mongodb_connection.connect()
    except PyMongoError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unhealthy"},
        )
    return {"status": "healthy", "service": "persistence-service"}


app.include_router(router)
