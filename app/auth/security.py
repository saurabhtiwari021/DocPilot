"""
Password hashing (bcrypt) and JWT access tokens.

This is the standard FastAPI auth pattern: passwords are never stored in
plaintext (only a bcrypt hash), and once a user logs in they get back a
short-lived signed JWT they attach as `Authorization: Bearer <token>` on
every subsequent request. `get_current_user` in dependencies.py decodes
and validates that token.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def hash_password(plain_password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str) -> str:
    """Create a signed JWT whose `sub` claim is the user's id."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> Optional[str]:
    """Return the user id encoded in the token, or None if invalid/expired."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except jwt.PyJWTError as exc:
        logger.info("Rejected invalid/expired JWT: %s", exc)
        return None
