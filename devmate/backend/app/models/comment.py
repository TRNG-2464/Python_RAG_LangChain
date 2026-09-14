"""
Comment model - day 1 plain-python version
Attaches to exactly one Ticket - the same one-to-many shape
that every later 'log entry' style model in this codebase will follow
"""

from datetime import datetime
from typing import ClassVar

class Comment:
    registry: ClassVar[list["Comment"]] = []

    def __init__(self, comment_id: int, ticket_id: int, author_id: int,
                 body: str, created_at: datetime | None = None):
        self.id = comment_id
        self.ticket_id = ticket_id
        self.author_id = author_id
        self.body = body
        self.created_at = created_at or datetime.now()
        Comment.registry.append(self)

    def __repr__(self) -> str:
        return (f"Comment(id={self.id}, ticket_id={self.ticket_id}, "
                f"author_id={self.author_id})")