"""
Day 1 demo script - Devmate application
run this file from the /backend directory using the following command:
    python -m scripts.day1_demo
"""

from datetime import date, timedelta

from app.models import Document, Ticket, Comment, DocumentCategory, TicketPriority, User

def find_team_mismatches(
        tickets: list[Ticket],
        documents: list[Document],
        users: list[User]
) -> list[tuple[Ticket, Document, User, User]]:
    """
    Day 1 phase b challenge answer key - answers business question #2
    team mismatch report - which tickets are assigned to a user whose team does NOT
    match the team of the user who owns the ticket's related document?
    """
    mismatches: list[tuple[Ticket, Document, User, User]] = []

    for ticket in tickets:
        if ticket.related_document_id is None:
            continue

        document = Document.find_by_id(ticket.related_document_id)
        assignee = User.find_by_id(ticket.assignee_id)

        """
        Defensive guard: a ticket that references a document_id or assignee_id
        that does not exist in the registry isn't a team mismatch, it is a data
        integrity issue. Here, we will skip it and add in a validation check later when
        we work with Pydantic
        """
        if document is None or assignee is None:
            continue

        owner = User.find_by_id(document.owner_id)
        if owner is None:
            continue

        if assignee.team != owner.team:
            mismatches.append((ticket, document, assignee, owner))

    return mismatches


def find_stale_documents(documents: list[Document], threshold: int = 90) -> list[Document]:
    """
    Business question #1 from DevMate problem statement document: Stale documentation report
    Which non-Postmortem documents haven't been reviewed in over 'threshold' days?
    """
    result = []
    for document in documents:
        if document.category != DocumentCategory.POSTMORTEM and document.is_stale(threshold):
            result.append(document)
    return result
    """
    return [
        document for document in documents:
        if document.category != DocumentCategory.POSTMORTEM
        and document.is_stale(threshold)
    ]"""

def seed_demo_data() -> None:

    today = date.today()

    Document(1, "Incident Response Runbook", DocumentCategory.RUNBOOK, body="Steps to triage a P1 incident...", owner_id=301,
             last_reviewed_at=today - timedelta(days=120)) #timedelta = "N days" as a subtractable amount
    Document(2, "Onboarding: Local Dev Setup", DocumentCategory.ONBOARDING, body="Clone the repo, run make setup...", owner_id=302,
             last_reviewed_at=today - timedelta(days=10))
    Document(3, "Q2 Outage Postmortem", DocumentCategory.POSTMORTEM, body="On May 3rd, the auth service...", owner_id=301,
             last_reviewed_at=today - timedelta(days=200))
    Document(4, "Deploy Pipeline Wiki", DocumentCategory.WIKI, body="Our CI/CD pipeline runs in three stages...", owner_id=303,
             last_reviewed_at=today - timedelta(days=95))

    Ticket(1, "Runbook missing rollback step", TicketPriority.HIGH, assignee_id=302, related_document_id=1)
    Ticket(2, "Wiki page has broken links", TicketPriority.LOW, assignee_id=303, related_document_id=4)

    Comment(1, ticket_id=1, author_id=301, body="Confirmed - step 4 references a script that no longer exists.")

    User(301, "A. Kim", team="SRE")
    User(302, "B. Osei", team="Platform")
    User(303, "C. Diaz", team="SRE")
    User(304, "D. Farah", team="SRE")



def main() -> None:
    seed_demo_data() #populate the in-memory registries with sample data

    print("== Full Document Registry ==")
    for document in Document.registry:
        print(document)

    print("\n== Stale Documentation Report (>90 days) ==")
    stale = find_stale_documents(Document.registry, threshold=100)
    if not stale:
        print(" No Stale Documents")
    for document in stale:
        print (f" STALE: {document.title!r} last reviewed "
               f"{document.days_since_last_reviewed()} days ago"
               f"({document.category.value})")

    print("\n== Team Mismatch Report ==")
    mismatches = find_team_mismatches(Ticket.registry, Document.registry, User.registry)
    if not mismatches:
        print(" No Mismatches Found ")
    for ticket, document, assignee, owner in mismatches:
        print(f"Ticket {ticket.id} ({ticket.title!r}) : "
              f"assignee {assignee.name} ({assignee.team}), "
              f"doc owner {owner.name} ({owner.team})")

if __name__ == "__main__":
    """
    This block only runs when the file is executed directly. For example, by our python -m scripts.day1_demo'
    command we listed above. Python sets the special __name__ variable to "__main__" only in the file we actually
    ran - any other file that IMPORTS this one instead sees __name__ equal to this module's own name, so main()
    won't just fire by importing it
    """
    main()