"""
Day 8 challenge script: queries the already-persisted Chroma vector db

run from the backend/ directory after day8_demo has been run at least once, with
our ollama models both running:
    python -m scripts.day8_challenge
"""

from app.rag.vector_store import search_documents

def main() -> None:
    query = "How do I get set up on my first day?"

    print(f"=== Unfiltered search ===\n")
    results = search_documents(query, k=3)
    for i, result in enumerate(results, start=1):
        print(f"--- Match{i} ---")
        print(f"Title: {result.metadata['title']} ({result.metadata['category']})")
        print(f"Chunk: {result.page_content!r}")

    print(f"=== Filtered to category='onboarding' ===\n")
    filtered_results = search_documents(query, k=3, category="Onboarding")
    for i, result in enumerate(filtered_results, start=1):
        print(f"--- Match{i} ---")
        print(f"Title: {result.metadata['title']} ({result.metadata['category']})")
        print(f"Chunk: {result.page_content!r}")

if __name__ == "__main__":
    main()