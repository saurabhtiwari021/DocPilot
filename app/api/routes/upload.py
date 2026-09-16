import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config.settings import get_settings
from app.database.db import get_db
from app.models.schemas import UploadResponse
from app.rate_limit import limiter
from app.services import document_registry
from app.services.document_loader import SUPPORTED_EXTENSIONS, load_single_document
from app.services.filenames import safe_filename
from app.services.storage_service import storage_service
from app.services.vectorstore_service import vectorstore_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])


async def _read_upload_within_limit(file: UploadFile, max_size_mb: int) -> bytes:
    """
    Read the upload in chunks, aborting as soon as it exceeds the
    configured limit - a bare `await file.read()` pulls the *entire*
    payload into memory first, which on a public endpoint means a
    handful of large uploads can exhaust the process's memory.
    """
    max_bytes = max_size_mb * 1024 * 1024
    chunks = []
    total = 0
    chunk_size = 1024 * 1024

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {max_size_mb}MB upload limit.",
            )
        chunks.append(chunk)

    return b"".join(chunks)


@router.post("/upload", response_model=UploadResponse)
@limiter.limit(get_settings().rate_limit_upload)
async def upload_document(
    request: Request,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a PDF, DOCX or TXT file. The file is stored (locally, or in
    AWS S3 when STORAGE_BACKEND=s3 - see app/services/storage_service.py)
    and its chunks are embedded and added incrementally to your own
    vector store - other users can never see or query it.

    Re-uploading a file with the same name replaces its previous chunks
    in the vector store instead of leaving stale copies behind.
    """
    settings = get_settings()

    # `file.filename` is attacker-controlled - never build a filesystem
    # or S3 path from it directly. safe_filename() strips any directory
    # components/traversal payloads and unexpected characters.
    filename = safe_filename(file.filename or "")
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        logger.info(
            "Rejected upload '%s' from user=%s: unsupported extension '%s'",
            filename, current_user.id, ext,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported types: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    contents = await _read_upload_within_limit(file, settings.max_upload_size_mb)
    content_hash = document_registry.sha256_of(contents)

    existing = document_registry.get_record(db, current_user.id, filename)
    if existing is not None and existing.content_hash == content_hash:
        # Identical re-upload - nothing changed, so skip re-embedding
        # (which would otherwise burn Gemini API quota for no reason).
        logger.info("Skipped re-indexing unchanged '%s' for user=%s", filename, current_user.id)
        return UploadResponse(
            filename=filename,
            chunks_indexed=len(document_registry.chunk_ids_of(existing)),
            message="This exact file is already indexed - no changes made.",
        )

    try:
        destination = await asyncio.to_thread(
            storage_service.save_file, current_user.id, filename, contents
        )
        documents = await asyncio.to_thread(load_single_document, destination)

        # Re-upload of a previously-seen filename: remove its old chunks
        # BEFORE indexing the new ones, so the store never holds both an
        # old and a new version of what is conceptually one document.
        if existing is not None:
            stale_ids = document_registry.chunk_ids_of(existing)
            await asyncio.to_thread(vectorstore_service.delete_documents, current_user.id, stale_ids)

        chunks_indexed, chunk_ids = await asyncio.to_thread(
            vectorstore_service.add_documents, current_user.id, documents
        )
        document_registry.upsert_record(db, current_user.id, filename, content_hash, chunk_ids)
    except HTTPException:
        raise
    except Exception:
        # Never leak internal exception details (stack traces, file
        # system paths, provider error messages) to the client.
        logger.error(
            "Failed to process upload '%s' for user=%s", filename, current_user.id, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to process the uploaded file.")

    logger.info(
        "Uploaded '%s' for user=%s: %d chunks indexed", filename, current_user.id, chunks_indexed
    )
    return UploadResponse(
        filename=filename,
        chunks_indexed=chunks_indexed,
        message="Document uploaded and indexed successfully.",
    )
