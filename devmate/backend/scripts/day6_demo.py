"""
Day 6 demo script: runs today's ticket-summary chain against real tickets already loaded by the 
existing ingeston layer, the same way day2_demo script exercised the loaders before any API existed

Run from the /backend directory using:
    python -m scripts.day6_demo
"""

from app.ai.chains import summarize_tickets
from app.ingestion.ticket_loader import load_tickets_from_csv


def main() -> None:
    tickets = load_tickets_from_csv("tickets.csv")
    for ticket in tickets:
        summary = summarize_tickets(
            title=ticket.title,
            priority=ticket.priority,
            status=ticket.status.value
        )
        print(f"[Ticket {ticket.id}] {summary}")


if __name__ == "__main__":
    main()
