from fastapi import APIRouter

from app.api.routes import auth, chat, documents, history, upload

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(upload.router)
api_router.include_router(chat.router)
api_router.include_router(history.router)
api_router.include_router(documents.router)
