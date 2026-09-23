"""
Day 8 Demo script: chunk, embed, and persist the real documents to the local Chroma
vector store, then run one similarity search against it.

Run from the /backend directory with ollama running BOTH models:
    python -m scripts.day8_demo
"""

from app.ingestion.document_loader import load_documents_from_folder
from app.rag.vector_store import build_vector_store

def main() -> None:
    documents = load_documents_from_folder("docs")
    vector_store = build_vector_store(documents)

    query = "What should I do first when a P1 incident starts?"
    results = vector_store.similarity_search(query, k=2)

    print(f"Query: {query!r}\n")
    for i, result in enumerate(results, start=1):
        print(f"--- Match {i} ---")
        print(f"Document: {result.metadata['title']} ({result.metadata['category']})")
        print(f"Chunk: {result.page_content!r}")

if __name__ == "__main__":
    main()