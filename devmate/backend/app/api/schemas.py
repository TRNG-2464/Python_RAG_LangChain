"""
Pydantic request/response schemas for the API layer

These are deliverately separate from app.models - the plain python domain classes
stay exactly as they are, and these BaseModel classes describe only what the API is willing
to show to a client.
"""

from datetime import date
from pydantic import BaseModel, ConfigDict

from app.models import DocumentCategory

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