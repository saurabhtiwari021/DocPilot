"""
RAG orchestration.

Wires together, per user:
- that user's persisted retriever from vectorstore_service (built once, not per request)
- the prompt templates from app/prompts/templates.py
- that user's conversation memory from memory_service.py
- source citations extracted from the retrieved chunks' metadata

using LangChain's history-aware retrieval chain, which:
1. Rewrites the incoming question using chat history (so "what about its diet?"
   becomes a standalone question before retrieval).
2. Retrieves relevant chunks with the rewritten question.
3. Answers strictly from those chunks using QA_PROMPT.

Chains are built lazily per user_id and cached, mirroring the
"build once" fix in vectorstore_service - a chain is only (re)built the
first time a given user asks a question.
"""

import asyncio
import logging
from typing import Dict, List

from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.settings import get_settings
from app.models.schemas import SourceCitation
from app.prompts.templates import CONTEXTUALIZE_Q_PROMPT, QA_PROMPT
from app.services.memory_service import get_session_history
from app.services.vectorstore_service import vectorstore_service

logger = logging.getLogger(__name__)


class RagService:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._chains: Dict[str, RunnableWithMessageHistory] = {}

    def _build_chain(self, user_id: str) -> RunnableWithMessageHistory:
        logger.info("Building RAG chain for user=%s (first question this session)", user_id)
        llm = ChatGoogleGenerativeAI(
            google_api_key=self._settings.google_api_key,
            model=self._settings.gemini_chat_model,
            temperature=0,
        )
        retriever = vectorstore_service.get_retriever(user_id)

        history_aware_retriever = create_history_aware_retriever(
            llm, retriever, CONTEXTUALIZE_Q_PROMPT
        )
        question_answer_chain = create_stuff_documents_chain(llm, QA_PROMPT)
        rag_chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

        return RunnableWithMessageHistory(
            rag_chain,
            lambda session_id: get_session_history(user_id, session_id),
            input_messages_key="input",
            history_messages_key="chat_history",
            output_messages_key="answer",
        )

    def _get_chain(self, user_id: str) -> RunnableWithMessageHistory:
        if user_id not in self._chains:
            self._chains[user_id] = self._build_chain(user_id)
        return self._chains[user_id]

    async def get_answer(self, user_id: str, query: str, session_id: str) -> Dict:
        try:
            chain = self._get_chain(user_id)
            # chain.invoke is synchronous (blocking network calls to
            # Gemini plus local FAISS/pgvector work). Running it directly
            # in an `async def` route would block the whole event loop -
            # i.e. every other request - for the duration of the call.
            result = await asyncio.to_thread(
                chain.invoke,
                {"input": query},
                config={"configurable": {"session_id": session_id}},
            )
        except Exception:
            logger.error("RAG chain invocation failed for user=%s session=%s", user_id, session_id, exc_info=True)
            raise

        sources: List[SourceCitation] = []
        for doc in result.get("context", []):
            metadata = doc.metadata or {}
            source_name = metadata.get("source", "unknown")
            sources.append(
                SourceCitation(
                    source=source_name.split("/")[-1].split("\\")[-1],
                    page=metadata.get("page"),
                    snippet=doc.page_content[:200].strip(),
                )
            )

        logger.info(
            "Answered query for user=%s session=%s using %d source chunks", user_id, session_id, len(sources)
        )
        return {
            "query": query,
            "answer": result["answer"],
            "sources": sources,
            "session_id": session_id,
        }


rag_service = RagService()
