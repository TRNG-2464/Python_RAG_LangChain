"""
Chunking, embedding, and storing for Devmate's documents in a local Chroma data store.

Nothing in this file talks to FastAPI, KnowledgeBaseService, or any other part of the app
- following our separation of concerns.
"""

from langchain_chroma import Chroma
from langchain_core.documents import Document as LCDocument
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.models import Document

CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "nomic-embed-text"
PERSIST_DIRECTORY = "chroma_db"

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP
)

_embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)

def _documents_to_metadata(document: Document) -> dict:
    """
    Chroma's underlying client only accepts str/int/float/bool metadata - 
    No None, no nested dicts, no lists. Last_reviewed_at is aplain python date
    object on our document model, so it has to be converted to a string here.
    """
    return {
        "document_id": document.id,
        "title": document.title,
        "category": document.category.value,
        "last_reviewed_at": document.last_reviewed_at.isoformat(),
    }

def documents_to_chunks(documents: list[Document]) -> list[LCDocument]:
    """
    this turns our Document objects into LangChain's document objects and
    splits them into chunks.
    """
    lc_documents = [
        LCDocument(page_content=document.body, metadata=_documents_to_metadata(document))
        for document in documents
    ]
    return _splitter.split_documents(lc_documents)

def build_vector_store(
        documents: list[Document], persist_directory: str = PERSIST_DIRECTORY
) -> Chroma:
    """
    Chunks, embeds, and persists the given documents to a fresh (or appended-to)
    chroma collection on the local disk. No separate .persist() calls, passing the 
    persist_directory here is enough and writes will land on the disk as they happen
    """
    chunks = documents_to_chunks(documents)
    return Chroma.from_documents(
        documents=chunks,
        embedding=_embeddings,
        persist_directory=persist_directory,
    )

def load_vector_store(persist_directory: str = PERSIST_DIRECTORY) -> Chroma:
    """
    Reopens an existing chroma collection without re-chunking or re-embedding anything
    """
    return Chroma(
        persist_directory=persist_directory,
        embedding_function=_embeddings
    )