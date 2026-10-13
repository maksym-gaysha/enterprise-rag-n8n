import asyncio
import logging
from typing import Sequence

from google import genai
from google.genai import errors, types

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiEmbeddingService:
    """Service for generating vector embeddings via Google GenAI."""

    EMBEDDING_DIM = 768

    def __init__(self, api_key: str | None = None, model_name: str | None = None):
        self._api_key = api_key or settings.GEMINI_API_KEY
        self._model_name = model_name or settings.EMBEDDING_MODEL
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

    async def generate_embeddings(
        self,
        texts: Sequence[str],
        batch_size: int = 32,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
    ) -> list[list[float]]:
        """
        Generate 768-dimensional embeddings for a batch of text chunks.
        Includes automatic chunk batching and exponential backoff retry logic.
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = list(texts[i : i + batch_size])
            batch_embeddings = await self._embed_batch_with_retry(
                batch=batch,
                max_retries=max_retries,
                initial_backoff=initial_backoff,
            )
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    async def _embed_batch_with_retry(
        self,
        batch: list[str],
        max_retries: int = 3,
        initial_backoff: float = 1.0,
    ) -> list[list[float]]:
        backoff = initial_backoff
        config = types.EmbedContentConfig(output_dimensionality=self.EMBEDDING_DIM)

        for attempt in range(1, max_retries + 1):
            try:
                response = await self.client.aio.models.embed_content(
                    model=self._model_name,
                    contents=batch,
                    config=config,
                )
                if not response.embeddings:
                    raise RuntimeError("Gemini API returned an empty embedding list.")

                vectors: list[list[float]] = []
                for embedding in response.embeddings:
                    if embedding.values is None or len(embedding.values) != self.EMBEDDING_DIM:
                        actual_dim = len(embedding.values) if embedding.values is not None else "None"
                        raise ValueError(
                            f"Unexpected embedding dimension: expected {self.EMBEDDING_DIM}, got {actual_dim}"
                        )
                    vectors.append(embedding.values)

                return vectors

            except Exception as exc:
                if isinstance(exc, errors.ClientError) and "API_KEY_INVALID" in str(exc):
                    logger.error("Gemini API key is invalid: %s", exc)
                    raise

                # Fallback if model is deprecated or not available for the account
                if "is not found" in str(exc) and self._model_name != "gemini-embedding-001":
                    logger.warning(
                        "Model '%s' not found. Falling back to 'gemini-embedding-001'...",
                        self._model_name,
                    )
                    self._model_name = "gemini-embedding-001"
                    continue

                logger.warning(
                    "Embedding generation failed on attempt %d/%d: %s. Retrying in %.1fs...",
                    attempt,
                    max_retries,
                    exc,
                    backoff,
                )
                if attempt == max_retries:
                    logger.error("Exceeded max retries for batch embedding: %s", exc, exc_info=True)
                    raise RuntimeError(
                        f"Gemini embedding generation failed after {max_retries} attempts: {exc}"
                    ) from exc

                await asyncio.sleep(backoff)
                backoff *= 2.0

        raise RuntimeError("Unexpected termination of embedding retry loop.")


gemini_service = GeminiEmbeddingService()
