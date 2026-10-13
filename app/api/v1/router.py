from fastapi import APIRouter

from app.api.v1.endpoints import documents, health

api_router = APIRouter()

# Mount routes under /api/v1
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])

