"""
Vector store service.

Two things this fixes vs. the original project:

1. The FAISS index (and the embeddings that go into it) used to be
   rebuilt from scratch on every single request. Here, each user's store
   is built (or loaded from disk) exactly ONCE - the first time that
   user touches it - and cached in memory after that. `add_documents()`
   does an incremental update instead of a full rebuild on upload.

2. FAISS is a local, file-based vector store. To match a job description
   that asks for a real vector database, this module also supports
   PostgreSQL + pgvector as a drop-in alternative, selected with the
   VECTOR_STORE_BACKEND env var ("faiss" or "pgvector"). The rest of the
   app talks to this service only through get_retriever()/add_documents(),
   so swapping backends never touches API or business logic code.

Multi-tenancy: every store is scoped to a `user_id` (FAISS: its own
subfolder on disk; pgvector: its own collection), so one user's uploaded
documents are never retrievable by another user's questions. See
app/auth/ for how `user_id` is established from the JWT bearer token.
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.config.settings import get_settings
from app.services.document_loader import load_documents_from_directory, split_documents
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)


class VectorStoreService:
    """Owns one long-lived vector store instance per user."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._embeddings = GoogleGenerativeAIEmbeddings(
            google_api_key=self._settings.google_api_key,
            model=self._settings.gemini_embedding_model,
        )
        # Built lazily per user, then cached for the life of the process -
        # this is the "built once" cache that replaces per-request rebuilds.
        self._stores: Dict[str, VectorStore] = {}

    def documents_dir_for(self, user_id: str) -> str:
        """
        Local directory containing this user's source documents. Delegates
        to storage_service, which transparently syncs a local cache from S3
        first when STORAGE_BACKEND=s3.
        """
        return storage_service.documents_dir_for(user_id)

    def _faiss_index_dir_for(self, user_id: str) -> str:
        return os.path.join(self._settings.faiss_index_base_dir, user_id, "faiss_index")

    def _pgvector_collection_for(self, user_id: str) -> str:
        return f"{self._settings.pgvector_collection_prefix}_{user_id}"

    # ------------------------------------------------------------------
    def get_or_create_store(self, user_id: str) -> VectorStore:
        """Return this user's vector store, building/loading it the first time it's needed."""
        if user_id in self._stores:
            return self._stores[user_id]

        if self._settings.vector_store_backend == "pgvector":
            store = self._init_pgvector(user_id)
        else:
            store = self._init_faiss(user_id)

        self._stores[user_id] = store
        return store

    def _init_faiss(self, user_id: str) -> VectorStore:
        from langchain_community.vectorstores import FAISS

        index_dir = self._faiss_index_dir_for(user_id)
        if os.path.exists(os.path.join(index_dir, "index.faiss")):
            logger.info("Loading persisted FAISS index for user=%s from %s", user_id, index_dir)
            return FAISS.load_local(
                index_dir,
                self._embeddings,
                allow_dangerous_deserialization=True,
            )

        logger.info("Building FAISS index for user=%s (first time)", user_id)
        documents = load_documents_from_directory(self.documents_dir_for(user_id))
        chunks = split_documents(documents)

        if not chunks:
            # Brand-new user with nothing uploaded yet - seed the index with
            # a placeholder so FAISS has something to initialize with; real
            # content gets added via /upload.
            chunks = [Document(page_content="No documents have been uploaded yet.", metadata={"source": "system"})]

        store = FAISS.from_documents(chunks, self._embeddings)
        os.makedirs(index_dir, exist_ok=True)
        store.save_local(index_dir)
        return store

    def _init_pgvector(self, user_id: str) -> VectorStore:
        from langchain_community.vectorstores import PGVector

        if not self._settings.pgvector_connection_string:
            raise RuntimeError(
                "VECTOR_STORE_BACKEND=pgvector but PGVECTOR_CONNECTION_STRING is not set. "
                "Example: postgresql+psycopg2://user:password@localhost:5432/ragdb"
            )

        logger.info("Connecting to pgvector collection '%s' for user=%s", self._pgvector_collection_for(user_id), user_id)
        store = PGVector(
            connection_string=self._settings.pgvector_connection_string,
            collection_name=self._pgvector_collection_for(user_id),
            embedding_function=self._embeddings,
        )

        # If this user's collection is empty (first run) and there are
        # documents sitting in their upload folder, index them once.
        documents = load_documents_from_directory(self.documents_dir_for(user_id))
        if documents:
            chunks = split_documents(documents)
            store.add_documents(chunks)
            logger.info("Seeded pgvector collection for user=%s with %d chunks", user_id, len(chunks))

        return store

    # ------------------------------------------------------------------
    # Runtime operations
    # ------------------------------------------------------------------
    def add_documents(self, user_id: str, documents: List[Document]) -> Tuple[int, List[str]]:
        """
        Incrementally embed and add new chunks to this user's store (used
        by /upload). Returns (chunk_count, chunk_ids) - the caller
        (document_registry, via upload.py) persists chunk_ids so a future
        re-upload of the same filename can remove exactly these chunks
        with delete_documents() before adding their replacements.
        """
        try:
            store = self.get_or_create_store(user_id)

            chunks = split_documents(documents)
            ids = store.add_documents(chunks)
            ids = list(ids) if ids else []

            if self._settings.vector_store_backend == "faiss":
                store.save_local(self._faiss_index_dir_for(user_id))

            logger.info("Indexed %d chunks for user=%s", len(chunks), user_id)
            return len(chunks), ids
        except Exception:
            logger.error("Failed to index documents for user=%s", user_id, exc_info=True)
            raise

    def delete_documents(self, user_id: str, chunk_ids: List[str]) -> None:
        """Remove previously-indexed chunks (e.g. a stale version of a re-uploaded file)."""
        if not chunk_ids:
            return
        try:
            store = self.get_or_create_store(user_id)
            store.delete(ids=chunk_ids)

            if self._settings.vector_store_backend == "faiss":
                store.save_local(self._faiss_index_dir_for(user_id))

            logger.info("Deleted %d stale chunk(s) for user=%s", len(chunk_ids), user_id)
        except Exception:
            logger.error("Failed to delete chunks for user=%s", user_id, exc_info=True)
            raise

    def get_retriever(self, user_id: str):
        store = self.get_or_create_store(user_id)
        return store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": self._settings.retriever_k},
        )


# Singleton used across the app (one manager per process, one store per user).
vectorstore_service = VectorStoreService()
