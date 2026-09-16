import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import hash_password, verify_password

logger = logging.getLogger(__name__)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def register_user(db: Session, username: str, password: str) -> User:
    if get_user_by_username(db, username) is not None:
        logger.info("Registration failed: username '%s' already taken", username)
        raise ValueError("Username is already taken.")

    user = User(username=username, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user id=%s username='%s'", user.id, user.username)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if user is None or not verify_password(password, user.hashed_password):
        logger.info("Authentication failed for username='%s'", username)
        return None
    return user
