"""
Document identity registry.

Fixes the re-upload bug where uploading a new version of an already-seen
file (e.g. "resume.pdf" twice) overwrote the physical file but left the
OLD version's vectors sitting in the vector store next to the new ones -
so a user's knowledge base could silently accumulate duplicate/contradictory
chunks for what looks, from the outside, like a single document.

Each (user_id, filename) pair now has exactly one DocumentRecord row that
remembers the ids of the chunks currently indexed for it. On re-upload,
upload.py deletes those old chunk ids from the vector store *before*
adding the new ones, and updates the row - so at any point in time there
is at most one set of chunks per user+filename.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database.db import Base

logger = logging.getLogger(__name__)


class DocumentRecord(Base):
    """Tracks one user's one logical document and its current chunk ids."""

    __tablename__ = "document_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # JSON-encoded list of vector-store chunk ids currently indexed for
    # this document, so a future re-upload/delete knows exactly what to
    # remove from the vector store.
    chunk_ids: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


def sha256_of(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()


def get_record(db: Session, user_id: str, filename: str) -> Optional[DocumentRecord]:
    return (
        db.query(DocumentRecord)
        .filter(DocumentRecord.user_id == user_id, DocumentRecord.filename == filename)
        .first()
    )


def upsert_record(
    db: Session,
    user_id: str,
    filename: str,
    content_hash: str,
    chunk_ids: List[str],
) -> DocumentRecord:
    record = get_record(db, user_id, filename)
    if record is None:
        record = DocumentRecord(user_id=user_id, filename=filename)
        db.add(record)

    record.content_hash = content_hash
    record.chunk_ids = json.dumps(chunk_ids)
    db.commit()
    db.refresh(record)
    logger.info(
        "Recorded document '%s' for user=%s: %d chunk(s), hash=%s",
        filename, user_id, len(chunk_ids), content_hash[:12],
    )
    return record


def delete_record(db: Session, user_id: str, filename: str) -> None:
    record = get_record(db, user_id, filename)
    if record is not None:
        db.delete(record)
        db.commit()


def chunk_ids_of(record: DocumentRecord) -> List[str]:
    try:
        return json.loads(record.chunk_ids or "[]")
    except (TypeError, ValueError):
        return []
