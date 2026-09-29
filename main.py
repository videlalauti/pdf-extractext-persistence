"""Persistence service FastAPI application: bootstrap y ciclo de vida de MongoDB."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from persistence.mongodb_connection import mongodb_connection
from routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongodb_connection.connect()
    yield
    await mongodb_connection.disconnect()


app = FastAPI(title="Document Persistence Service", version="1.0.0", lifespan=lifespan)


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
