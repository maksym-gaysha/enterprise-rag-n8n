import asyncio
import logging
import uuid
from typing import Sequence

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.schemas.chat import ChatQueryRequest, ChatResponse, SourceReference
from app.services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


def make_excerpt(text: str, max_chars: int = 250) -> str:
    """Create a clean, bounded excerpt from chunk text."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + "..."


class RAGService:
    """Retrieval-Augmented Generation Service using pgvector cosine distance and Gemini LLM."""

    SYSTEM_INSTRUCTION = (
        "You are an accurate enterprise AI assistant. "
        "Answer the user question strictly using only the provided excerpts. "
        "Do not fabricate facts. "
        "If the information is missing from the context, clearly acknowledge that it cannot be found in the provided documentation."
    )

    SIMILARITY_THRESHOLD = 0.35

    def __init__(self, api_key: str | None = None, llm_model: str | None = None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._llm_model = llm_model or settings.LLM_MODEL
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        effective_key = self._api_key or settings.GEMINI_API_KEY
        if not effective_key:
            raise ValueError(
                "GEMINI_API_KEY is not configured. Please set GEMINI_API_KEY in your environment or .env file."
            )
        if self._client is None or self._api_key != effective_key:
            self._api_key = effective_key
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def search_similar_chunks(
        self,
        db: AsyncSession,
        query_vector: list[float],
        top_k: int = 4,
        document_id: uuid.UUID | None = None,
    ) -> list[tuple[DocumentChunk, Document, float]]:
        """
        Perform vector similarity search using cosine distance (<=>).
        Returns list of (chunk, document, similarity_score).
        """
        distance_expr = DocumentChunk.embedding.cosine_distance(query_vector).label("distance")

        stmt = (
            select(DocumentChunk, Document, distance_expr)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.status == DocumentStatus.READY)
        )

        if document_id is not None:
            stmt = stmt.where(Document.id == document_id)

        stmt = stmt.order_by(distance_expr.asc()).limit(top_k)

        result = await db.execute(stmt)
        rows = result.all()

        scored_chunks: list[tuple[DocumentChunk, Document, float]] = []
        for chunk, doc, distance in rows:
            # Cosine distance: 0 (identical) to 2 (opposite).
            # Similarity = 1.0 - distance, bounded between 0 and 1.
            raw_sim = 1.0 - float(distance)
            sim_score = max(0.0, min(1.0, round(raw_sim, 3)))
            scored_chunks.append((chunk, doc, sim_score))

        return scored_chunks

    async def generate_grounded_answer(
        self,
        question: str,
        context_blocks: Sequence[str],
        max_retries: int = 3,
    ) -> str:
        """
        Generate answer from Gemini using strictly provided context.
        Includes automatic fallback across candidate models if primary model is unavailable.
        """
        formatted_context = "\n\n".join(context_blocks)
        user_prompt = (
            f"Context Excerpts:\n"
            f"-----------------\n"
            f"{formatted_context}\n"
            f"-----------------\n\n"
            f"User Question:\n"
            f"{question}\n\n"
            f"Answer:"
        )

        config = types.GenerateContentConfig(
            system_instruction=self.SYSTEM_INSTRUCTION,
            temperature=0.2,
        )

        candidate_models = [
            self._llm_model,
            "gemini-3.5-flash-lite",
            "gemini-3.8-flash",
            "gemini-3.5-flash",
        ]
        unique_models: list[str] = []
        for m in candidate_models:
            if m and m not in unique_models:
                unique_models.append(m)

        last_error: Exception | None = None

        for model_candidate in unique_models:
            backoff = 1.0
            for attempt in range(1, max_retries + 1):
                try:
                    response = await self.client.aio.models.generate_content(
                        model=model_candidate,
                        contents=user_prompt,
                        config=config,
                    )
                    if response.text:
                        self._llm_model = model_candidate
                        return response.text.strip()
                    raise RuntimeError("Gemini returned an empty response.")

                except Exception as exc:
                    last_error = exc
                    if "is not found" in str(exc) or "no longer available" in str(exc):
                        logger.warning(
                            "Model '%s' is not available (%s). Trying next candidate...",
                            model_candidate,
                            exc,
                        )
                        break

                    logger.warning(
                        "Generation with model '%s' failed on attempt %d/%d: %s. Retrying in %.1fs...",
                        model_candidate,
                        attempt,
                        max_retries,
                        exc,
                        backoff,
                    )
                    if attempt == max_retries:
                        break
                    await asyncio.sleep(backoff)
                    backoff *= 2.0

        raise RuntimeError(f"All LLM generation candidates failed: {last_error}") from last_error

    async def query(
        self,
        db: AsyncSession,
        request: ChatQueryRequest,
    ) -> ChatResponse:
        """
        Full RAG pipeline:
        1. Embed question.
        2. Vector search matching top_k chunks using cosine distance (<=>).
        3. Check similarity threshold (>= 0.35).
        4. Assemble context & cite sources.
        5. Generate grounded answer via Gemini LLM.
        """
        logger.info("Generating embedding for question: %s", request.question)
        embeddings = await gemini_service.generate_embeddings([request.question])
        if not embeddings or not embeddings[0]:
            raise RuntimeError("Failed to compute embedding for query.")

        query_vector = embeddings[0]

        scored_chunks = await self.search_similar_chunks(
            db=db,
            query_vector=query_vector,
            top_k=request.top_k,
            document_id=request.document_id,
        )

        if not scored_chunks or scored_chunks[0][2] < self.SIMILARITY_THRESHOLD:
            logger.info("No chunks matched similarity threshold (%s)", self.SIMILARITY_THRESHOLD)
            return ChatResponse(
                answer="I could not find any relevant information in the provided documentation to answer your question.",
                confidence="low",
                sources=[],
            )

        context_blocks: list[str] = []
        sources: list[SourceReference] = []

        for idx, (chunk, doc, score) in enumerate(scored_chunks, start=1):
            page_label = f"Page {chunk.page_number}" if chunk.page_number else "N/A"
            context_blocks.append(
                f"[Source {idx} | Document: {doc.filename} | {page_label}]\n{chunk.chunk_text}"
            )
            sources.append(
                SourceReference(
                    document_name=doc.filename,
                    page_number=chunk.page_number,
                    excerpt=make_excerpt(chunk.chunk_text),
                    similarity_score=score,
                )
            )

        max_score = scored_chunks[0][2]
        if max_score >= 0.75:
            confidence = "high"
        elif max_score >= 0.55:
            confidence = "medium"
        else:
            confidence = "low"

        logger.info(
            "Generating answer from %d retrieved chunks (max similarity: %.3f)...",
            len(sources),
            max_score,
        )
        answer = await self.generate_grounded_answer(
            question=request.question,
            context_blocks=context_blocks,
        )

        return ChatResponse(
            answer=answer,
            confidence=confidence,
            sources=sources,
        )


rag_service = RAGService()
