"""
Conversation memory.

Each `user_id` + `session_id` pair gets its own chat history, persisted
with SQLAlchemy (SQLite by default, but the URL is configurable) via
LangChain's SQLChatMessageHistory. Namespacing by user_id means two
different logged-in users can both use session_id="default" without
ever seeing each other's conversation - authentication (see app/auth/)
is what makes that isolation trustworthy, not just convention.

This history is what powers both:
- multi-turn context in the RAG chain (see rag_service.py)
- the GET /history and DELETE /history endpoints
"""

import logging

from langchain_community.chat_message_histories import SQLChatMessageHistory

from app.database.db import get_engine

logger = logging.getLogger(__name__)


def _namespaced_session_id(user_id: str, session_id: str) -> str:
    return f"{user_id}:{session_id}"


def get_session_history(user_id: str, session_id: str) -> SQLChatMessageHistory:
    """Return the persisted chat history for a given user's session."""
    return SQLChatMessageHistory(
        session_id=_namespaced_session_id(user_id, session_id),
        connection=get_engine(),
    )


def clear_session_history(user_id: str, session_id: str) -> None:
    get_session_history(user_id, session_id).clear()
    logger.info("Cleared conversation history for user=%s session=%s", user_id, session_id)
