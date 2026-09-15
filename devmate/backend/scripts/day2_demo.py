"""
Demo script: Devmate
Run from the /backend directory using the following command:
    python -m scripts.day2_demo
"""

from app.models import Document, DocumentCategory
from app.ingestion.document_loader import load_documents_from_folder


def find_stale_documents(documents: list[Document], threshold: int = 90) -> list[Document]:
    """
    This function answers business question #1 from Devmate's problem statement document
    """
    return [
        document for document in documents
        if document.category != DocumentCategory.POSTMORTEM
        and document.is_stale(threshold)
    ]

def main() -> None:
    print("== Loading docs/ ==")
    documents = load_documents_from_folder("docs")

    print(f"\n== Loaded {len(documents)} Document(s) ==")
    for document in documents:
        print(document)

    print("\n== Stale Documentation Report (> 90 days) ==")
    stale = find_stale_documents(documents, threshold=90)
    if not stale:
        print(" No stale documents")
    for document in stale:
        print(f" STALE: {document.title!r} last reviewed "
              f"{document.days_since_last_reviewed()} days ago "
              f"({document.category.value})")

if __name__ == "__main__":
    main()