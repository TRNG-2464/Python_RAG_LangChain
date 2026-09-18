"""
Dependency injection providers for the API layer
"""

from functools import lru_cache

from app.ingestion.document_loader import load_documents_from_folder
from app.analytics.workload import compute_team_workload
from app.ingestion.ticket_loader import load_tickets_from_csv
from app.models import Document, DocumentCategory, Ticket, User

def _find_team_mismatches(
        tickets: list[Ticket],
        documents: list[Document],
        users: list[User]
) -> list[tuple[Ticket, Document, User, User]]:
    """
    This answers business question #2
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


class KnowledgeBaseService:
    """Owns the in-memory Document collection and answers questions about it"""
    def __init__(self, documents: list[Document], tickets: list[Ticket], users: list[User]):
        self._documents = documents
        self._tickets = tickets
        self._users = users

    def get_all_documents(self) -> list[Document]:
        return self._documents

    def get_stale_documents(self, threshold: int = 90) -> list[Document]:
        return [
            document for document in self._documents
            if document.category != DocumentCategory.POSTMORTEM
            and document.is_stale(threshold)
        ]

    def get_document_by_id(self, document_id: int) -> Document | None:
        for document in self._documents:
            if document.id == document_id:
                return document
        return None
    
    """This owns the ticket portion"""
    def get_all_tickets(self) -> list[Ticket]:
        return self._tickets

    def get_team_mismatches(self) -> list[tuple[Ticket, Document, User, User]]:
        return _find_team_mismatches(self._tickets, self._documents, self._users)

    def get_ticket_by_id(self, ticket_id: int) -> Ticket | None:
        for ticket in self._tickets:
            if ticket.id == ticket_id:
                return ticket
        return None

    def get_team_workload_report(self) -> dict:
        return compute_team_workload(self._tickets, self._users)

def _seed_users() -> list[User]:
    return[
        User(301, "A. Kim", team="SRE"),
        User(302, "B. Osei", team="Platform"),
        User(303, "C. Diaz", team="SRE"),
        User(304, "D. Farah", team="SRE")
    ]

@lru_cache
def get_knowledge_base_service() -> KnowledgeBaseService:
    """
    FastAPI dependency provider

    @lru_cache means the /docs folder is only loaded from disk the first time
    this is called, and every later Depends(get_knowledge_base_service) across
    every request reuses the same cached KnowledgeBaseService instance, instead
    of re-running every file on every request
    """
    documents = load_documents_from_folder("docs")
    tickets = load_tickets_from_csv("tickets.csv")
    users = _seed_users()
    return KnowledgeBaseService(documents, tickets, users)