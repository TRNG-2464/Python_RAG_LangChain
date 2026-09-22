"""
Day 7 demo script: exercises structured output, conversation memory, and tool calling against
a real ticket, the same way we did yesterday, just with extra steps.

Run from the /backend directory with Ollama running (`ollama serve`):
    python -m scripts.day7_demo
"""

from langchain_core.messages import AIMessage, HumanMessage

from app.ai.chains import (
    ask_about_ticket_document,
    ask_ticket_followup,
    suggest_ticket_triage
)
from app.ingestion.ticket_loader import load_tickets_from_csv
from app.ingestion.document_loader import load_documents_from_folder
from app.models import Ticket

def main() -> None:
    load_tickets_from_csv("tickets.csv")
    load_documents_from_folder("docs")
    ticket = Ticket.get_by_id(1)

    print("=== Structured Output: independent triage suggestion ===")
    suggestion = suggest_ticket_triage(title=ticket.title, status=ticket.status.value)
    print(f"suggested_priority = {suggestion.suggested_priority!r}")
    print(f"needs_escalation = {suggestion.needs_escalation!r}")
    print(f"reasoning = {suggestion.reasoning!r}")
    print(f"(actual ticket priority for comparison: {ticket.priority.value})")

    print("\n=== Conversation memory: two follow-up turns, same history ===")
    ticket_context = f"{ticket.title} ({ticket.status.value})"
    history: list = []

    question_1 = "In one sentence, what's this ticket about?"
    answer_1 = ask_ticket_followup(ticket_context, history, question_1)
    print(f"Q1: {question_1}\nA1: {answer_1}")
    history.append(HumanMessage(content=question_1))
    history.append(AIMessage(content=answer_1))

    question_2 = "Does that still sound like something worth escalating?"
    answer_2 = ask_ticket_followup(ticket_context, history, question_2)
    print(f"Q2: {question_2}\nA2: {answer_2}")
    history.append(HumanMessage(content=question_2))
    history.append(AIMessage(content=answer_2))


    print("\n=== Tool calling: asking about a ticket's related document ===")
    question_3 = "What document does this ticket relate to, ans what kind of document is it?"
    answer_3 = ask_about_ticket_document(
        title=ticket.title,
        related_document_id=ticket.related_document_id,
        question=question_3
    )
    print(f"Q3: {question_3}\nA3: {answer_3}")


if __name__ == "__main__":
    main()
