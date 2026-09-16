"""
File storage service.

Uploaded documents (PDF/DOCX/TXT) have to live *somewhere* before they can
be parsed and embedded. Two backends are supported, selected with the
STORAGE_BACKEND env var - the same pattern already used for vector store
backends in vectorstore_service.py ("faiss" vs "pgvector"):

- "local" (default): files are saved to disk under
  DOCUMENTS_BASE_DIR/<user_id>/, exactly like the original project.

- "s3": files are uploaded to an AWS S3 bucket under
  s3://<S3_BUCKET_NAME>/<user_id>/<filename>. S3 is the durable source of
  truth in this mode - nothing under DOCUMENTS_BASE_DIR is required to
  survive a restart or a redeploy.

  The document loaders (PyPDFLoader / Docx2txtLoader / TextLoader) only
  know how to read a local file path, so when the S3 backend is active
  this service transparently downloads a working copy into LOCAL_CACHE_DIR
  before handing a path back to the caller. The rest of the app
  (upload.py, documents.py, vectorstore_service.py) never has to know
  which backend is active - it only calls the methods below.
"""

import logging
import os
from dataclasses import dataclass
from typing import List

from app.config.settings import get_settings
from app.services.filenames import safe_filename

logger = logging.getLogger(__name__)


@dataclass
class StoredFile:
    filename: str
    size_bytes: int
    uploaded_at: str  # ISO 8601


class StorageService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._s3_client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @property
    def _use_s3(self) -> bool:
        return self._settings.storage_backend == "s3"

    def _s3(self):
        """Lazily create (and cache) the boto3 S3 client."""
        if self._s3_client is None:
            import boto3

            logger.info("Initializing S3 client (region=%s)", self._settings.aws_region)
            self._s3_client = boto3.client(
                "s3",
                region_name=self._settings.aws_region,
                aws_access_key_id=self._settings.aws_access_key_id or None,
                aws_secret_access_key=self._settings.aws_secret_access_key or None,
            )
        return self._s3_client

    def _s3_prefix(self, user_id: str) -> str:
        return f"{user_id}/"

    def _s3_key(self, user_id: str, filename: str) -> str:
        return f"{user_id}/{filename}"

    def _local_documents_dir(self, user_id: str) -> str:
        path = os.path.join(self._settings.documents_base_dir, user_id)
        os.makedirs(path, exist_ok=True)
        return path

    def _local_cache_dir(self, user_id: str) -> str:
        path = os.path.join(self._settings.local_cache_dir, user_id)
        os.makedirs(path, exist_ok=True)
        return path

    # ------------------------------------------------------------------
    # Public API used by the API routes / vectorstore service
    # ------------------------------------------------------------------
    def documents_dir_for(self, user_id: str) -> str:
        """
        Local directory that holds a *working copy* of this user's
        documents - used by document_loader.load_documents_from_directory
        to (re)build a vector store. For the local backend this is the
        permanent home of the files; for S3 it's a synced cache.
        """
        if self._use_s3:
            self.sync_cache_from_s3(user_id)
            return self._local_cache_dir(user_id)
        return self._local_documents_dir(user_id)

    def save_file(self, user_id: str, filename: str, contents: bytes) -> str:
        """
        Persist an uploaded file's bytes and return a local path the
        document loaders can immediately parse.

        `filename` is defensively re-sanitized here even though callers
        (upload.py) already sanitize it - this is the last line of
        defense against path traversal before a filesystem/S3 path is
        built from attacker-controlled input.
        """
        filename = safe_filename(filename)
        if self._use_s3:
            key = self._s3_key(user_id, filename)
            logger.info(
                "Uploading '%s' to s3://%s/%s (%d bytes)",
                filename, self._settings.s3_bucket_name, key, len(contents),
            )
            try:
                self._s3().put_object(
                    Bucket=self._settings.s3_bucket_name,
                    Key=key,
                    Body=contents,
                )
            except Exception:
                logger.error(
                    "Failed to upload '%s' to S3 bucket '%s'",
                    filename, self._settings.s3_bucket_name, exc_info=True,
                )
                raise

            # Keep a local scratch copy too, so the caller (upload.py) can
            # immediately parse + embed it without a round trip back to S3.
            local_path = os.path.join(self._local_cache_dir(user_id), filename)
            with open(local_path, "wb") as f:
                f.write(contents)
            return local_path

        local_path = os.path.join(self._local_documents_dir(user_id), filename)
        with open(local_path, "wb") as f:
            f.write(contents)
        logger.info("Saved '%s' locally at %s (%d bytes)", filename, local_path, len(contents))
        return local_path

    def list_documents(self, user_id: str) -> List[StoredFile]:
        """List every document currently stored for this user."""
        if self._use_s3:
            prefix = self._s3_prefix(user_id)
            logger.info("Listing s3://%s/%s", self._settings.s3_bucket_name, prefix)
            files: List[StoredFile] = []
            try:
                # list_objects_v2 caps results at 1000 keys per call - a
                # user with more documents than that would silently see
                # only the first page. The paginator walks every page.
                paginator = self._s3().get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=self._settings.s3_bucket_name, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        filename = obj["Key"][len(prefix):]
                        if not filename:
                            continue
                        files.append(
                            StoredFile(
                                filename=filename,
                                size_bytes=obj["Size"],
                                uploaded_at=obj["LastModified"].isoformat(),
                            )
                        )
            except Exception:
                logger.error("Failed to list S3 objects under prefix '%s'", prefix, exc_info=True)
                raise
            return files

        import datetime

        directory = self._local_documents_dir(user_id)
        files = []
        for filename in sorted(os.listdir(directory)):
            path = os.path.join(directory, filename)
            if not os.path.isfile(path):
                continue
            stat = os.stat(path)
            files.append(
                StoredFile(
                    filename=filename,
                    size_bytes=stat.st_size,
                    uploaded_at=datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                )
            )
        return files

    def sync_cache_from_s3(self, user_id: str) -> None:
        """
        Make sure every object this user has in S3 also has a local
        scratch copy in LOCAL_CACHE_DIR - needed the first time a user's
        vector store is (re)built after a restart, since only S3 is
        guaranteed to have survived. No-op for the local backend.
        """
        if not self._use_s3:
            return

        prefix = self._s3_prefix(user_id)
        cache_dir = self._local_cache_dir(user_id)
        try:
            paginator = self._s3().get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._settings.s3_bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    filename = obj["Key"][len(prefix):]
                    if not filename:
                        continue
                    local_path = os.path.join(cache_dir, filename)
                    if os.path.exists(local_path) and os.path.getsize(local_path) == obj["Size"]:
                        continue  # already cached
                    logger.info(
                        "Downloading s3://%s/%s to %s", self._settings.s3_bucket_name, obj["Key"], local_path
                    )
                    self._s3().download_file(self._settings.s3_bucket_name, obj["Key"], local_path)
        except Exception:
            logger.error("Failed to list S3 objects for cache sync (user=%s)", user_id, exc_info=True)
            raise


# Singleton used across the app, same pattern as vectorstore_service.
storage_service = StorageService()
