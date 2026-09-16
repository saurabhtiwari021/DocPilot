import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.models.schemas import ChatMessageOut, HistoryResponse
from app.services.memory_service import clear_session_history, get_session_history

logger = logging.getLogger(__name__)

router = APIRouter(tags=["History"])


@router.get("/history", response_model=HistoryResponse)
async def get_history(session_id: str = "default", current_user: User = Depends(get_current_user)):
    """Return your persisted conversation history for a session."""
    try:
        history = get_session_history(current_user.id, session_id)
        messages = [ChatMessageOut(role=m.type, content=m.content) for m in history.messages]
        return HistoryResponse(session_id=session_id, messages=messages)
    except Exception:
        logger.error(
            "Failed to fetch history for user=%s session=%s", current_user.id, session_id, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to fetch history.")


@router.delete("/history")
async def delete_history(session_id: str = "default", current_user: User = Depends(get_current_user)):
    """Clear your conversation history for a session."""
    try:
        clear_session_history(current_user.id, session_id)
        logger.info("Cleared history for user=%s session=%s", current_user.id, session_id)
        return {"session_id": session_id, "message": "History cleared."}
    except Exception:
        logger.error(
            "Failed to clear history for user=%s session=%s", current_user.id, session_id, exc_info=True
        )
        raise HTTPException(status_code=500, detail="Failed to clear history.")
