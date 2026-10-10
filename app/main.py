import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import close_db, init_db

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enterprise_rag")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    Executes database schema & extension verification at startup,
    and cleanly disposes connections on shutdown.
    """
    logger.info("Starting up %s (env: %s)...", settings.PROJECT_NAME, settings.ENVIRONMENT)
    await init_db()
    yield
    logger.info("Shutting down %s...", settings.PROJECT_NAME)
    await close_db()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="Enterprise RAG Microservice with PostgreSQL & pgvector",
    lifespan=lifespan,
    docs_url=f"{settings.API_V1_STR}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_STR}/redoc" if settings.DEBUG else None,
    openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
)

# Root-level healthcheck endpoint: GET /health
app.include_router(health_router, tags=["Health"])

# Versioned API routes: GET /api/v1/...
app.include_router(api_router, prefix=settings.API_V1_STR)
