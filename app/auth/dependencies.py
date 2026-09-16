from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import decode_access_token
from app.database.db import get_db

# tokenUrl points at the login route so FastAPI's interactive docs (/docs)
# render an "Authorize" button that logs in and attaches the token for you.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    user_id = decode_access_token(token)
    if user_id is None:
        raise credentials_exception

    user = db.get(User, user_id)
    if user is None:
        raise credentials_exception

    return user
