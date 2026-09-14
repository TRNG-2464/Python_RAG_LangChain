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