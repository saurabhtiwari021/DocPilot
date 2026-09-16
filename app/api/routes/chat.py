import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.config.settings import get_settings
from app.models.schemas import ChatRequest, ChatResponse
from app.rate_limit import limiter
from app.services.rag_service import rag_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(get_settings().rate_limit_chat)
async def chat(request: Request, body: ChatRequest, current_user: User = Depends(get_current_user)):
    """
    Ask a question about YOUR uploaded documents only. Conversation
    history is tracked per `session_id` within your account, so
    follow-up questions ("what about...?") are understood in context.
    """
    logger.info("Chat request from user=%s session=%s", current_user.id, body.session_id)
    try:
        result = await rag_service.get_answer(current_user.id, body.query, body.session_id)
        return ChatResponse(**result)
    except Exception:
        # Never leak internal exception details (provider errors, stack
        # traces) to the client - log them, return a generic message.
        logger.error(
            "Chat request failed for user=%s session=%s", current_user.id, body.session_id, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to answer the question.")
