import logging

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    database: str
    pgvector: bool


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System and Database Healthcheck",
    description="Queries PostgreSQL to verify connection and validates that the pgvector extension is active.",
)
async def check_health(db: AsyncSession = Depends(get_db)):
    try:
        # Check database connectivity
        await db.execute(text("SELECT 1;"))

        # Verify pgvector extension is installed
        result = await db.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');")
        )
        is_pgvector_active: bool = bool(result.scalar())

        if not is_pgvector_active:
            logger.warning("Database connected but 'vector' extension is not present.")
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "degraded",
                    "database": "connected",
                    "pgvector": False,
                },
            )

        return HealthResponse(
            status="healthy",
            database="connected",
            pgvector=True,
        )
    except Exception as exc:
        logger.error("Database healthcheck failed: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "pgvector": False,
            },
        )
