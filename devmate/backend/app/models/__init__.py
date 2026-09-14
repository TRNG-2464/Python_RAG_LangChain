"""
Package init lets us write:
    from app.models import Document, Ticket
instead of:
    from app.models.document import Document
    from app.models.ticket import Ticket
"""

from .enums import DocumentCategory, TicketStatus, TicketPriority
from .document import Document
from .ticket import Ticket
from .comment import Comment
from .user import User

"""
__all__ declares this package's public surface - similar to choosing what is public
vs private in Java, although Python only enforces this for 'from app.models import *'
"""
__all__ = [
    "DocumentCategory", "TicketStatus", "TicketPriority",
    "Document", "Ticket", "Comment", "User",
]