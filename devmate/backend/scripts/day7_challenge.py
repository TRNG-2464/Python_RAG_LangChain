"""
Day 7 challenge script: exercise structured output, conversation
memory, and tool calling against one real document, the same way
day7_demo.py exercised all three against a real ticket.

Run from backend\\, with Ollama running (`ollama serve`, or the
desktop app's background service) and the venv active:
    python -m scripts.day7_challenge
"""

from langchain_core.messages import AIMessage, HumanMessage

from app.ai.chains import (
    ask_about_document_owner,
    ask_document_followup,
    suggest_document_health,
)
from app.ingestion.document_loader import load_documents_from_folder
from app.models import Document, User


def main() -> None:
    # Loading documents alone is NOT enough here - look_up_document_owner
    # needs User.registry populated too, exactly the same lesson the
    # demo script's missing load_documents_from_folder(...) call
    # taught with tickets. Same four users deps.py's _seed_users seeds.
    load_documents_from_folder("docs")
    User(301, "A. Kim", team="SRE")
    User(302, "B. Osei", team="Platform")
    User(303, "C. Diaz", team="SRE")
    User(304, "D. Farah", team="SRE")

    document = Document.find_by_id(2)

    print("=== Structured output: independent health assessment ===")
    assessment = suggest_document_health(
        title=document.title,
        category=document.category.value,
        days_since_reviewed=document.days_since_last_reviewed(),
    )
    print(f"is_stale_risk      = {assessment.is_stale_risk!r}")
    print(f"recommended_action = {assessment.recommended_action!r}")
    print(f"reasoning          = {assessment.reasoning!r}")

    print("\n=== Conversation memory: two follow-up turns, same history ===")
    document_context = f"{document.title} ({document.category.value})"
    history: list = []

    question_1 = "In one sentence, what does this document cover?"
    answer_1 = ask_document_followup(document_context, history, question_1)
    print(f"Q1: {question_1}\nA1: {answer_1}")
    history.append(HumanMessage(content=question_1))
    history.append(AIMessage(content=answer_1))

    question_2 = "Does it sound like something a new engineer would need?"
    answer_2 = ask_document_followup(document_context, history, question_2)
    print(f"\nQ2: {question_2}\nA2: {answer_2}")

    print("\n=== Tool calling: asking about the document's owner ===")
    question_3 = "Who owns this document, and what team are they on?"
    answer_3 = ask_about_document_owner(
        title=document.title,
        owner_id=document.owner_id,
        question=question_3,
    )
    print(f"Q3: {question_3}\nA3: {answer_3}")


if __name__ == "__main__":
    main()

