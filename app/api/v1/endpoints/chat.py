import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.chat import ChatQueryRequest, ChatResponse
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/query",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Query document knowledge base",
    description=(
        "Performs vector similarity search via pgvector cosine distance (<=>), "
        "assembles contextual excerpts with page citations, and generates a grounded, "
        "hallucination-free answer using Google Gemini."
    ),
)
async def query_chat(
    request: ChatQueryRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await rag_service.query(db=db, request=request)
    except ValueError as val_err:
        logger.error("Configuration error during RAG query: %s", val_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("RAG query failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the query: {exc}",
        )
