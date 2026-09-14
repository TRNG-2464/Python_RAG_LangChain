"""
Document model - Day 1 plain-python version
No DB, and state lives only on the 'registry' class attribute
"""

from datetime import date
from typing import ClassVar #lets us type-hint a class-level (Shared) attribute

from .enums import DocumentCategory

class Document:

    """
    class attributes - declared here, OUTSIDE our __init__ - are shared by every document instance
    think of this as the Python equivalent of a 'static' field in Java: there is only ONE 'registry' 
    list, and every document ever created gets appended to the same list
    """
    registry: ClassVar[list["Document"]] = []
    STALE_THRESHOLD_DAYS: ClassVar[int] = 90

    #methods with leading and trailing double underscores are referred to as 'Dunder' methods
    #__init__() is the same as a constructor in Java, self='this' keyword in Java
    def __init__(self, document_id: int, title: str, category: DocumentCategory, 
                 body: str, owner_id: int, last_reviewed_at: date | None = None):
        self.id = document_id
        self.title = title
        self.category = category
        self.body = body
        self.owner_id = owner_id
        self.last_reviewed_at = last_reviewed_at or date.today()
        Document.registry.append(self) #automatically add our new document object to the registry

    def days_since_last_reviewed(self, as_of: date | None = None) -> int:
        today = as_of or date.today()
        return (today - self.last_reviewed_at).days

    def is_stale(self, threshold: int | None = None, as_of: date | None = None) -> bool:
        """
        saying if threshold is not none, then use the threshold value passed in the parameters
        of the is_stale function. Or ELSE, use the document class's STALE_THRESHOLD_DAYS constant
        This is an example of if-else shorthand
        """
        limit = threshold if threshold is not None else Document.STALE_THRESHOLD_DAYS
        return self.days_since_last_reviewed(as_of) > limit

    @classmethod #receives the CLASS itself as 'cls', not an instance
    def find_by_id(cls, document_id: int) -> "Document | None":
        for document in cls.registry:
            if document.id == document_id:
                return document
        return None #represents no match found

    def __repr__(self) -> str:
        """
        repr controls what shows up when you 'print()' an object
        or what shows in a debugger when you inspect it - similar to
        overriding the toString() method in Java
        """
        return (f"Document(id={self.id}, title={self.title!r}, "
                f"category={self.category.value}, "
                f"last_reviewed_at={self.last_reviewed_at.isoformat()})")
    