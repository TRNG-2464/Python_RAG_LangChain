"""
Dependency injection providers for the API layer
"""

from functools import lru_cache

from app.ingestion.document_loader import load_documents_from_folder
from app.models import Document, DocumentCategory

class KnowledgeBaseService:
    """Owns the in-memory Document collection and answers questions about it"""
    def __init__(self, documents: list[Document]):
        self._documents = documents

    def get_all_documents(self) -> list[Document]:
        return self._documents

    def get_stale_documents(self, threshold: int = 90) -> list[Document]:
        return [
            document for document in self._documents
            if document.category != DocumentCategory.POSTMORTEM
            and document.is_stale(threshold)
        ]

@lru_cache
def get_knowledge_base_service() -> KnowledgeBaseService:
    """
    FastAPI dependency provider

    @lru_cache means the /docs folder is only loaded from disk the first time
    this is called, and every later Depends(get_knowledge_base_service) across
    every request reuses the same cached KnowledgeBaseService instance, instead
    of re-running every file on every request
    """
    documents = load_documents_from_folder("docs")
    return KnowledgeBaseService(documents)