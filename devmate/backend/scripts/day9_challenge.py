"""
Day 9 challenge script: query the vector db with a confidence threshold,
so that weak matches are dropped instead of always returned

Run from backend/ directory:
    python -m scripts.day9_challenge
"""

from app.rag.retriever import format_retrieved_context, get_threshold_retriever


def main() -> None:
    query = "What should I do first when a P1 incident starts?"

    print("=== Lenient Threshold (score_threshold=0.3) ===\n")
    lenient_retriever = get_threshold_retriever(score_threshold=0.3)
    lenient_results = lenient_retriever.invoke(query)
    print(f"{len(lenient_results)} result(s) cleared the threshold: ")
    for result in lenient_results:
        print(f" - {result.metadata['title']}")
    print("\nFormatted context for whatever cleared the threshold: \n")
    print(format_retrieved_context(lenient_results))

    print("\n=== Strict Threshold (score_threshold=0.9) ===\n")
    strict_retriever = get_threshold_retriever(score_threshold=0.9)
    strict_results = strict_retriever.invoke(query)
    print(f"{len(strict_results)} result(s) cleared the threshold: ")
    for result in strict_results:
        print(f" - {result.metadata['title']}")
    print("\nFormatted context for whatever cleared the threshold: \n")
    print(format_retrieved_context(strict_results))

if __name__ == "__main__":
    main()
