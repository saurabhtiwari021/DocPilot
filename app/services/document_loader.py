"""
Document loading.

The original project only supported a single hardcoded .txt file via
TextLoader. This service supports PDF, DOCX and TXT, and can load either
a single uploaded file or an entire directory of previously uploaded
documents.
"""

import logging
import os
from typing import List

from langchain_community.document_loaders import (
    Docx2txtLoader,
    DirectoryLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Maps a file extension to the LangChain loader class responsible for it.
LOADER_MAPPING = {
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader,
    ".txt": TextLoader,
}

SUPPORTED_EXTENSIONS = tuple(LOADER_MAPPING.keys())


def _get_loader_for_file(file_path: str):
    ext = os.path.splitext(file_path)[1].lower()
    loader_cls = LOADER_MAPPING.get(ext)
    if loader_cls is None:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported types: {', '.join(SUPPORTED_EXTENSIONS)}"
        )
    if loader_cls is TextLoader:
        return loader_cls(file_path, encoding="utf-8")
    return loader_cls(file_path)


def load_single_document(file_path: str) -> List[Document]:
    """Load one file (pdf/docx/txt) into a list of LangChain Documents."""
    logger.info("Loading document '%s'", file_path)
    loader = _get_loader_for_file(file_path)
    try:
        documents = loader.load()
    except Exception:
        logger.error("Failed to load document '%s'", file_path, exc_info=True)
        raise
    logger.info("Loaded %d page(s)/section(s) from '%s'", len(documents), file_path)
    return documents


def load_documents_from_directory(directory: str) -> List[Document]:
    """
    Load every supported document in `directory`.

    Uses DirectoryLoader per extension (it only accepts a single loader
    class at a time) and merges the results, so PDFs, DOCX and TXT files
    can all live side by side in data/documents/.
    """
    documents: List[Document] = []
    if not os.path.isdir(directory):
        return documents

    for ext, loader_cls in LOADER_MAPPING.items():
        loader_kwargs = {"encoding": "utf-8"} if loader_cls is TextLoader else {}
        dir_loader = DirectoryLoader(
            directory,
            glob=f"**/*{ext}",
            loader_cls=loader_cls,
            loader_kwargs=loader_kwargs,
            show_progress=False,
            use_multithreading=True,
        )
        documents.extend(dir_loader.load())

    return documents


def split_documents(documents: List[Document]) -> List[Document]:
    """Split documents into overlapping chunks for embedding."""
    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )
    return splitter.split_documents(documents)
