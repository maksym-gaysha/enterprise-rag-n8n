from fastapi import APIRouter

from app.api.v1.endpoints import health

api_router = APIRouter()

# Mount health routes under /api/v1
api_router.include_router(health.router, tags=["Health"])
