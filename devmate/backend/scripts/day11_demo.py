"""
Day 11 demo script: run several turns of one conversation through a retrieval chain via ask_with_memory

Run from the /backend directory with .venv running and Ollama running:
    python -m scripts.day11_demo
"""

from app.rag.qa_chain import ConversationMemory, ask_with_memory

def main() -> None:
    memory = ConversationMemory()

    questions = [
        "What should I do first when a P1 incident starts?",
        "Who should I notify besides the on-call SRE?",
        "How long did the Q2 outage last?",
        "What caused it?"
    ]

    for i, question in enumerate(questions, start=1):
        result = ask_with_memory(memory, question)
        print(f"--- Turn {i} ---")
        print(f"Q: {question}")
        print(f"A: {result.answer}")
        print(f"Sources: {result.sources}")
        print(f"Summary after this turn: {memory.summary!r}")
        print(f"Raw recent messages kept: {len(memory.recent_messages)}")
        print()

if __name__ == "__main__":
    main()