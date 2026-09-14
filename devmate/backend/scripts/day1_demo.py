"""
Day 1 demo script - Devmate application
run this file from the /backend directory using the following command:
    python -m scripts.day1_demo
"""

from datetime import date, timedelta

from app.models import Document, Ticket, Comment, DocumentCategory, TicketPriority

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

if __name__ == "__main__":
    """
    This block only runs when the file is executed directly. For example, by our python -m scripts.day1_demo'
    command we listed above. Python sets the special __name__ variable to "__main__" only in the file we actually
    ran - any other file that IMPORTS this one instead sees __name__ equal to this module's own name, so main()
    won't just fire by importing it
    """
    main()