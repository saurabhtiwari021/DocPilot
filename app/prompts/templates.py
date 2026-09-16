"""
Prompt Engineering
-------------------
All prompts the RAG pipeline uses live here instead of being inlined as a
raw f-string. Two prompts are needed for a *conversational* RAG system:

1. CONTEXTUALIZE_Q_PROMPT
   Rewrites a follow-up question ("what about its diet?") into a
   standalone question ("what does a polar bear eat?") using the chat
   history, BEFORE it hits the retriever. This is what makes multi-turn
   conversations actually retrieve the right chunks.

2. QA_PROMPT
   The actual answering prompt. It is instructed to answer strictly from
   the retrieved context and to say "I don't know" rather than
   hallucinating when the answer isn't in the documents.
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

CONTEXTUALIZE_Q_SYSTEM_PROMPT = (
    "Given a chat history and the latest user question which might "
    "reference context in the chat history, formulate a standalone "
    "question which can be understood without the chat history. "
    "Do NOT answer the question, just reformulate it if needed and "
    "otherwise return it as is."
)

CONTEXTUALIZE_Q_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CONTEXTUALIZE_Q_SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

QA_SYSTEM_PROMPT = (
    "You are DocPilot, an AI assistant answering questions about the "
    "documents a user has uploaded.\n\n"
    "Rules:\n"
    "- Only answer using the provided context below.\n"
    "- If the answer is not contained in the context, say "
    '"I don\'t know based on the provided documents." '
    "Do not make up information.\n"
    "- Be concise and cite specific facts from the context where possible.\n\n"
    "Context:\n{context}"
)

QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", QA_SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)
