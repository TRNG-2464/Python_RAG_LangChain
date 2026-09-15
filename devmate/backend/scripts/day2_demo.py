"""
Demo script: Devmate
Run from the /backend directory using the following command:
    python -m scripts.day2_demo

Falsey values: 0, null, None, NoneType, empty strings, empty lists(any empty collection)    
Truthy values: everything else
"""

from app.models import Document, DocumentCategory, Ticket, User
from app.ingestion.document_loader import load_documents_from_folder
from app.ingestion.ticket_loader import load_tickets_from_csv


def find_team_mismatches(
        tickets: list[Ticket],
        documents: list[Document],
        users: list[User]
) -> list[tuple[Ticket, Document, User, User]]:
    """
    This function answers business question #2 from Devmate's problem statement document
    """
    mismatches: list[tuple[Ticket, Document, User, User]] = []

    for ticket in tickets:
        if ticket.related_document_id is None:
            continue

        document = Document.find_by_id(ticket.related_document_id)
        assignee = User.find_by_id(ticket.assignee_id)

        if document is None or assignee is None:
            continue

        owner = User.find_by_id(document.owner_id)
        if owner is None:
            continue

        if assignee.team != owner.team:
            mismatches.append((ticket, document, assignee, owner))

    return mismatches

def seed_users() -> None:
    User(301, "A. Kim", team="SRE")
    User(302, "B. Osei", team="Platform")
    User(303, "C. Diaz", team="SRE")
    User(304, "D. Farah", team="SRE")


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
    seed_users()

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

    print("\n== Loading tickets.csv ==")
    tickets = load_tickets_from_csv("tickets.csv")
    print(f" Loaded {len(tickets)} Ticket(s)")

    print("\n== Team Mismatch Report ==")
    mismatches = find_team_mismatches(tickets, documents, User.registry)
    if not mismatches:
        print(" No mismatches found")

    for ticket, document, assignee, owner in mismatches:
        print(f" Ticket {ticket.id} ({ticket.title!r}) : "
              f"assignee {assignee.name} ({assignee.team}), "
              f"doc owner {owner.name} ({owner.team})")

if __name__ == "__main__":
    main()