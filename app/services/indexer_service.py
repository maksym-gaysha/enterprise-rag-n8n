import logging
import os
import uuid
from typing import Any

from pypdf import PdfReader
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.gemini_service import gemini_service

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str) -> list[tuple[int, str]]:
    """
    Extract text page-by-page from a PDF file.
    Returns a list of (page_number, text) tuples (1-indexed).
    """
    pages_data: list[tuple[int, str]] = []
    reader = PdfReader(file_path)
    for idx, page in enumerate(reader.pages):
        page_num = idx + 1
        page_text = page.extract_text() or ""
        if page_text.strip():
            pages_data.append((page_num, page_text.strip()))
    return pages_data


def extract_text_from_txt(file_path: str) -> list[tuple[int, str]]:
    """
    Read text from a plain text file.
    Returns [(1, text)].
    """
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    if content.strip():
        return [(1, content.strip())]
    return []


def extract_text(file_path: str, filename: str) -> list[tuple[int, str]]:
    """Route file to appropriate extractor based on extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    else:
        raise ValueError(f"Unsupported file format: {ext}")


def recursive_split_text(
    text: str,
    chunk_size: int = 700,
    chunk_overlap: int = 100,
    separators: list[str] | None = None,
) -> list[str]:
    """
    Split text recursively by boundary separators to target chunk_size
    with chunk_overlap characters while keeping natural semantic boundaries.
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    chosen_sep = separators[-1]
    for sep in separators:
        if sep == "" or sep in text:
            chosen_sep = sep
            break

    splits = text.split(chosen_sep) if chosen_sep else list(text)
    next_separators = (
        separators[separators.index(chosen_sep) + 1 :]
        if chosen_sep in separators and chosen_sep != ""
        else [""]
    )

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for part in splits:
        piece = part + chosen_sep if chosen_sep else part
        piece_len = len(piece)

        if piece_len > chunk_size and next_separators:
            sub_chunks = recursive_split_text(part, chunk_size, chunk_overlap, next_separators)
            for sub_piece in sub_chunks:
                if current_chunk:
                    combined = "".join(current_chunk).strip()
                    if combined:
                        chunks.append(combined)
                    current_chunk = []
                    current_len = 0
                chunks.append(sub_piece)
            continue

        if current_len + piece_len > chunk_size and current_chunk:
            combined = "".join(current_chunk).strip()
            if combined:
                chunks.append(combined)

            if chunk_overlap > 0:
                overlap_text = combined[-chunk_overlap:]
                space_pos = overlap_text.find(" ")
                if 0 <= space_pos < len(overlap_text) // 2:
                    overlap_text = overlap_text[space_pos + 1 :]
                current_chunk = [overlap_text, piece]
                current_len = len(overlap_text) + piece_len
            else:
                current_chunk = [piece]
                current_len = piece_len
        else:
            current_chunk.append(piece)
            current_len += piece_len

    if current_chunk:
        combined = "".join(current_chunk).strip()
        if combined and (not chunks or combined != chunks[-1]):
            chunks.append(combined)

    return chunks


def chunk_document_pages(
    pages_data: list[tuple[int, str]],
    chunk_size: int = 700,
    chunk_overlap: int = 100,
) -> list[dict[str, Any]]:
    """
    Chunk document pages sequentially, preserving originating page numbers.
    """
    all_chunks: list[dict[str, Any]] = []
    chunk_idx = 0

    for page_num, page_text in pages_data:
        page_chunks = recursive_split_text(
            page_text,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        for chunk in page_chunks:
            clean_chunk = chunk.strip()
            if not clean_chunk:
                continue
            all_chunks.append({
                "chunk_text": clean_chunk,
                "page_number": page_num,
                "chunk_index": chunk_idx,
            })
            chunk_idx += 1

    return all_chunks


async def process_document_background(document_id: uuid.UUID, file_path: str) -> None:
    """
    Background ingestion task.
    CRITICAL: Always opens a fresh session via async_session_maker() to avoid
    closed-session race conditions from request lifecycles.
    """
    logger.info("Starting background ingestion for document %s...", document_id)

    async with async_session_maker() as session:
        try:
            # 1. Fetch target document
            stmt = select(Document).where(Document.id == document_id)
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            if not document:
                logger.error("Document with id %s was not found.", document_id)
                return

            # 2. Extract text per page
            pages_data = extract_text(file_path, document.filename)
            if not pages_data:
                raise ValueError("No extractable text found in uploaded file.")

            # 3. Boundary-aware recursive chunking
            chunks_meta = chunk_document_pages(pages_data, chunk_size=700, chunk_overlap=100)
            if not chunks_meta:
                raise ValueError("Text extracted but no valid chunks could be created.")

            logger.info(
                "Document %s: extracted %d pages, created %d chunks.",
                document_id,
                len(pages_data),
                len(chunks_meta),
            )

            # 4. Generate 768-dim embeddings via Google GenAI
            chunk_texts = [c["chunk_text"] for c in chunks_meta]
            embeddings = await gemini_service.generate_embeddings(chunk_texts)

            # 5. Persist chunks with pgvector embeddings
            db_chunks = [
                DocumentChunk(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    chunk_text=meta["chunk_text"],
                    page_number=meta["page_number"],
                    chunk_index=meta["chunk_index"],
                    embedding=emb,
                )
                for meta, emb in zip(chunks_meta, embeddings)
            ]
            session.add_all(db_chunks)

            # 6. Mark document as READY
            document.status = DocumentStatus.READY
            document.chunks_count = len(db_chunks)
            document.error_message = None
            await session.commit()

            logger.info(
                "Background ingestion completed successfully for document %s (%d chunks saved).",
                document_id,
                len(db_chunks),
            )

        except Exception as exc:
            logger.error("Background ingestion failed for document %s: %s", document_id, exc, exc_info=True)
            await session.rollback()
            try:
                # Update status to FAILED
                stmt = select(Document).where(Document.id == document_id)
                res = await session.execute(stmt)
                doc_to_fail = res.scalar_one_or_none()
                if doc_to_fail:
                    doc_to_fail.status = DocumentStatus.FAILED
                    doc_to_fail.error_message = str(exc)
                    await session.commit()
            except Exception as update_err:
                logger.error("Failed to update FAILED status for document %s: %s", document_id, update_err)

        finally:
            # Clean up the uploaded temporary file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.debug("Removed temporary file %s", file_path)
                except OSError as err:
                    logger.warning("Could not remove temporary file %s: %s", file_path, err)
