import logging
import os
import tempfile
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.document import Document, DocumentStatus
from app.schemas.document import (
    DocumentListItem,
    DocumentListResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.indexer_service import process_document_background

logger = logging.getLogger(__name__)

router = APIRouter()

SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload document for ingestion",
    description="Uploads a PDF or TXT file, creates a document record with status PROCESSING, and enqueues background ingestion.",
)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty.",
        )

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Read contents and calculate size
    content = await file.read()
    file_size = len(content)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # Save to a temporary file for background processing
    temp_dir = tempfile.gettempdir()
    temp_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_filepath = os.path.join(temp_dir, temp_filename)

    with open(temp_filepath, "wb") as f:
        f.write(content)

    # Create document record in database
    document = Document(
        id=uuid.uuid4(),
        filename=file.filename,
        file_size=file_size,
        status=DocumentStatus.PROCESSING,
        chunks_count=0,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Enqueue background ingestion task with isolated session handling
    background_tasks.add_task(
        process_document_background,
        document.id,
        temp_filepath,
    )

    logger.info("Enqueued background processing for document: %s (id: %s)", document.filename, document.id)

    return DocumentUploadResponse(
        document_id=document.id,
        filename=document.filename,
        file_size=document.file_size,
        status=document.status,
        message="Document accepted for background processing.",
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Get document processing status",
    description="Returns current processing status, number of generated chunks, and error message if failed.",
)
async def get_document_status(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).where(Document.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} was not found.",
        )

    return DocumentStatusResponse(
        document_id=document.id,
        filename=document.filename,
        file_size=document.file_size,
        status=document.status,
        chunks_count=document.chunks_count,
        error_message=document.error_message,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List all documents",
    description="Lists all uploaded documents with status and metadata.",
)
async def list_documents(
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Document).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    documents = result.scalars().all()

    items = [
        DocumentListItem(
            id=doc.id,
            filename=doc.filename,
            file_size=doc.file_size,
            status=doc.status,
            chunks_count=doc.chunks_count,
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in documents
    ]

    return DocumentListResponse(
        total=len(items),
        documents=items,
    )
