import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.models.schemas import DocumentInfo, DocumentsResponse
from app.services.document_loader import SUPPORTED_EXTENSIONS
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Documents"])


@router.get("/documents", response_model=DocumentsResponse)
async def list_documents(current_user: User = Depends(get_current_user)):
    """
    List every document currently indexed in YOUR knowledge base (reads
    from local disk or AWS S3 depending on STORAGE_BACKEND).
    """
    try:
        stored_files = storage_service.list_documents(current_user.id)
    except Exception:
        logger.error("Failed to list documents for user=%s", current_user.id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list documents.")

    documents = [
        DocumentInfo(filename=f.filename, size_bytes=f.size_bytes, uploaded_at=f.uploaded_at)
        for f in stored_files
        if os.path.splitext(f.filename)[1].lower() in SUPPORTED_EXTENSIONS
    ]

    return DocumentsResponse(documents=documents, count=len(documents))
