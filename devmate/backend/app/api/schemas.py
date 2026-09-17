"""
Pydantic request/response schemas for the API layer

These are deliverately separate from app.models - the plain python domain classes
stay exactly as they are, and these BaseModel classes describe only what the API is willing
to show to a client.
"""

from datetime import date
from pydantic import BaseModel, ConfigDict

from app.models import DocumentCategory, TicketPriority, TicketStatus

class DocumentOut(BaseModel):
    """
    from_attributes=True (this is the Pydantic V2 name for the old ORM_mode)
    lets DocumentOut.model_validate(some_document) read values off a plain object's
    Attributes (document.id, document.title...) instead of requiring a dict. Without
    this, model_validate will require a dict, not any old Python object.
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: DocumentCategory
    owner_id: int
    last_reviewed_at: date

class StaleDocumentOut(BaseModel):
    id: int
    title: str
    category: DocumentCategory
    days_since_last_reviewed: int

class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    priority: TicketPriority
    status: TicketStatus
    assignee_id: int
    related_document_id: int | None

class MismatchOut(BaseModel):
    """
    a mismatch isn't just one object, it's a ticket, a document, and
    two users
    """
    ticket_id: int
    ticket_title: str
    assignee_name: str
    assignee_team: str
    owner_name: str
    owner_team: str

"""
A pagination 'envelope' - the actual page of results, plus enough metadata(total, skip, limit)
for a client to know whether or not there is more to fetch, without the need for a second request
"""
class DocumentPage(BaseModel):
    items: list[DocumentOut]
    total: int
    skip: int
    limit: int

class TicketPage(BaseModel):
    items: list[TicketOut]
    total: int
    skip: int
    limit: int