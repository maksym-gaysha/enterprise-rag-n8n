import logging
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy 2.0 Async Engine with pool pinging enabled
engine = create_async_engine(
    settings.async_database_url,
    echo=settings.DEBUG,
    pool_pre_ping=True,
)

# Async Session Factory
async_session_maker = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database extensions and verify connectivity."""
    logger.info("Initializing database, verifying pgvector extension and creating tables...")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        from app.models import Base
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema and pgvector extension successfully initialized.")


async def close_db() -> None:
    """Cleanly dispose of the database engine connection pool."""
    logger.info("Disposing database connection pool...")
    await engine.dispose()
    logger.info("Database connection pool disposed.")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session per request."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()
