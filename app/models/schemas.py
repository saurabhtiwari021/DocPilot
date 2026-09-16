"""Request and response models shared across the API."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SourceCitation(BaseModel):
    """A single supporting chunk returned alongside an answer."""

    source: str = Field(..., description="Original file name the chunk came from")
    page: Optional[int] = Field(None, description="Page number, when the source format has pages (e.g. PDF)")
    snippet: str = Field(..., description="Short excerpt of the retrieved chunk")


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="The user's question")
    session_id: str = Field(
        default="default",
        description="Conversation/session identifier, used to keep chat history separate per user",
    )


class ChatResponse(BaseModel):
    query: str
    answer: str
    sources: List[SourceCitation]
    session_id: str


class ChatMessageOut(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: List[ChatMessageOut]


class DocumentInfo(BaseModel):
    filename: str
    size_bytes: int
    uploaded_at: str


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    message: str


class DocumentsResponse(BaseModel):
    documents: List[DocumentInfo]
    count: int
