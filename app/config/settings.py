"""
Centralized configuration for DocPilot.

Everything that used to be a hardcoded value or scattered os.getenv() call
now lives here, loaded once from environment variables / .env file via
pydantic-settings.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Runtime environment: "development" or "production". Controls
    # startup safety checks (e.g. refusing to boot without a real
    # JWT_SECRET_KEY) - see app/main.py's lifespan handler. ---
    environment: str = "development"

    # --- Google Gemini ---
    google_api_key: str = ""
    gemini_chat_model: str = "gemini-2.0-flash"
    # NOTE: models/text-embedding-004 was shut down by Google on
    # 2026-01-14. gemini-embedding-001 (or the newer gemini-embedding-2,
    # where available) are the current stable replacements. Changing this
    # value means any existing FAISS/pgvector indexes were built with a
    # different embedding space and MUST be rebuilt, not just reused.
    gemini_embedding_model: str = "gemini-embedding-001"

    # --- Text splitting ---
    chunk_size: int = 500
    chunk_overlap: int = 50

    # --- Retrieval ---
    retriever_k: int = 5

    # --- Vector store backend: "faiss" (default, file-based) or "pgvector" ---
    vector_store_backend: str = "faiss"

    # FAISS (persisted to disk so it is built once, not on every request).
    # Each user gets their own subfolder: <faiss_index_base_dir>/<user_id>/
    faiss_index_base_dir: str = "data/vectorstore"

    # pgvector (PostgreSQL + the pgvector extension). Each user gets their
    # own collection: <pgvector_collection_prefix>_<user_id>
    pgvector_connection_string: Optional[str] = None
    pgvector_collection_prefix: str = "docpilot"

    # --- Source documents. Each user gets their own subfolder:
    # <documents_base_dir>/<user_id>/
    documents_base_dir: str = "data/documents"

    # --- Upload limits (defense against a public endpoint being used to
    # exhaust memory/disk/API quota). ---
    max_upload_size_mb: int = 20

    # --- File storage backend: "local" (default, disk-based) or "s3" ---
    # See app/services/storage_service.py.
    storage_backend: str = "local"

    # AWS S3 (only used when storage_backend == "s3"). Credentials can also
    # be provided the normal boto3 way (shared credentials file, IAM role,
    # etc.) instead of via env vars - these are just an explicit override.
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    s3_bucket_name: str = ""

    # Local scratch space used to hold a working copy of a file that lives
    # in S3, since the PDF/DOCX/TXT loaders need a real local path to parse.
    local_cache_dir: str = "data/cache"

    # --- App database: users + conversation memory (SQLAlchemy / SQLite
    # by default, but any SQLAlchemy URL works, e.g. Postgres in prod). ---
    app_db_url: str = "sqlite:///./data/app.db"

    # --- Auth / JWT ---
    # No random fallback here on purpose: a secret regenerated on every
    # process restart means every previously-issued token silently stops
    # working, and with multiple workers/instances each would sign with
    # a *different* random secret, so a token minted by one worker would
    # fail validation on another. app/main.py's startup check refuses to
    # boot in production if this is left blank.
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- CORS ---
    # Comma-separated list of allowed origins, e.g.
    # "https://docpilot.example.com,https://app.docpilot.example.com".
    # Left as "*" only for local development - app/main.py logs a
    # warning (and refuses to boot in production) if this is still "*".
    frontend_url: str = "*"

    # --- Rate limiting (protects /auth/*, /upload and /chat, which is
    # the endpoint that burns Gemini API quota per call). ---
    rate_limit_auth: str = "10/minute"
    rate_limit_upload: str = "20/minute"
    rate_limit_chat: str = "30/minute"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Settings are read once and cached for the lifetime of the process."""
    return Settings()


def ensure_production_safety(settings: Settings) -> None:
    """
    Fail fast on startup if the app is misconfigured for a real deployment.

    Called from app/main.py's lifespan handler. In development this only
    logs warnings (so `git clone && uvicorn ...` still works out of the
    box); in production it raises, which stops the app from starting
    rather than silently running with an insecure/incorrect config.
    """
    import logging
    import secrets

    logger = logging.getLogger(__name__)
    is_prod = settings.environment.lower() == "production"

    if not settings.jwt_secret_key:
        message = (
            "JWT_SECRET_KEY is not set. Every process restart (and every "
            "additional worker/instance) would then sign tokens with a "
            "different random secret, breaking existing sessions and "
            "cross-worker validation."
        )
        if is_prod:
            raise RuntimeError(f"Refusing to start in production: {message}")
        logger.warning(
            "%s Using a random per-process secret for this dev run only.",
            message,
        )
        settings.jwt_secret_key = secrets.token_urlsafe(32)

    if settings.frontend_url == "*":
        message = (
            "FRONTEND_URL/CORS is set to allow all origins ('*'). Set it "
            "to your actual frontend origin(s) before going live."
        )
        if is_prod:
            raise RuntimeError(f"Refusing to start in production: {message}")
        logger.warning(message)

