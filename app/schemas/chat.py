import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The question to query against the document knowledge base.",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        description="Optional document ID to restrict retrieval scope.",
    )
    top_k: int = Field(
        default=4,
        ge=1,
        le=10,
        description="Maximum number of chunks to retrieve for context assembly.",
    )


class SourceReference(BaseModel):
    document_name: str = Field(
        ...,
        description="Originating document filename.",
    )
    page_number: int | None = Field(
        default=None,
        description="Originating document page number (if available).",
    )
    excerpt: str = Field(
        ...,
        description="Representative text snippet from the retrieved chunk.",
    )
    similarity_score: float = Field(
        ...,
        description="Similarity score (1.0 - cosine_distance) rounded to 3 decimal places.",
    )


class ChatResponse(BaseModel):
    answer: str = Field(
        ...,
        description="Hallucination-free answer generated strictly from retrieved context.",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level based on highest chunk similarity score.",
    )
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="List of cited source documents and excerpt snippets.",
    )
