"""
Day 9 demo script: wraps the already-persisted chroma db as similarity and mmr retrievers,
and formats their results into a context string

run from the backend/ directory after the day8_demo script has been run at least once, with
our ollama models active:
    python -m scripts.day9_demo
"""

from app.rag.retriever import (
    format_retrieved_context,
    get_diverse_retriever,
    get_similarity_retriever
)

def main() -> None:
    query = "What should I do first when a P1 incident starts?"

    print("=== Similarity Retriever ===\n")
    similarity_retriever = get_similarity_retriever(k=3)
    similarity_results = similarity_retriever.invoke(query)
    for i, result in enumerate(similarity_results, start=1):
        print(f"--- Match {i}, {result.metadata['title']} ({result.metadata['category']}) ---")

    print("\nFormatted Context (ready to hand off to our LLM tomorrow): \n")
    print(format_retrieved_context(similarity_results))

    print("\n=== MMR Retriever (same query, re-ranked for diveristy) ===\n")
    diverse_retriever = get_diverse_retriever(k=3, lambda_mult=0.2)
    diverse_results = diverse_retriever.invoke(query)
    for i, result in enumerate(diverse_results, start=1):
        print(f"--- Match {i}, {result.metadata['title']} ({result.metadata['category']}) ---")

if __name__ == "__main__":
    main()