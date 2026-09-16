import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth.schemas import RegisterRequest, Token, UserOut
from app.auth.security import create_access_token
from app.auth.service import authenticate_user, register_user
from app.config.settings import get_settings
from app.database.db import get_db
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(get_settings().rate_limit_auth)
async def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    """Create a new account. Every user gets their own documents, vector index, and chat history."""
    try:
        user = register_user(db, body.username, body.password)
    except ValueError as exc:
        logger.info("Registration rejected for username='%s': %s", body.username, exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.info("Registered new user id=%s username='%s'", user.id, user.username)
    return UserOut(id=user.id, username=user.username)


@router.post("/login", response_model=Token)
@limiter.limit(get_settings().rate_limit_auth)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Log in with username + password (standard OAuth2 password form so the
    /docs 'Authorize' button works out of the box) and get back a JWT
    Bearer token to use on /upload, /chat, /history and /documents.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        logger.info("Failed login attempt for username='%s'", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(subject=user.id)
    logger.info("User id=%s username='%s' logged in", user.id, user.username)
    return Token(access_token=access_token)
