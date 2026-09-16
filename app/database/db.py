"""
Database layer.

A single SQLAlchemy engine backs two things:
- the `users` table (app/auth/models.py), for registration/login
- conversation history (app/services/memory_service.py, via LangChain's
  SQLChatMessageHistory)

Centralizing the connection here means every part of the app that
touches the database goes through one place, and makes it easy to swap
SQLite for Postgres/MySQL by changing a single env var (APP_DB_URL).
"""

import logging
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker] = None


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models (see app/auth/models.py)."""
    pass


def get_engine() -> Engine:
    """Lazily create (and cache) the SQLAlchemy engine for the app database."""
    global _engine
    if _engine is None:
        settings = get_settings()
        logger.info("Creating database engine for %s", settings.app_db_url)
        connect_args = {"check_same_thread": False} if settings.app_db_url.startswith("sqlite") else {}
        _engine = create_engine(settings.app_db_url, connect_args=connect_args)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def get_db() -> Session:
    """FastAPI dependency that yields a database session and closes it after the request."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (called once at startup)."""
    Base.metadata.create_all(bind=get_engine())
    logger.info("Database tables ready.")
