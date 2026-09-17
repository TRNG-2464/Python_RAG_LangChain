"""
holds our /tickets routes
"""

from fastapi import APIRouter, Depends, Query, status, HTTPException

from app.api.deps import KnowledgeBaseService, get_knowledge_base_service
from app.api.schemas import MismatchOut, TicketOut, TicketPage
from app.api.security import require_api_key

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_api_key)]
)

@router.get("", response_model=TicketPage, status_code=status.HTTP_200_OK)
def list_tickets(
    skip: int = Query(0, ge=0, description="Number of tickets to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max tickets to return"),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> TicketPage:
    all_tickets = service.get_all_tickets()
    page = all_tickets[skip: skip + limit]
    return TicketPage(
        items=[TicketOut.model_validate(ticket) for ticket in page],
        total=len(all_tickets),
        skip=skip,
        limit=limit
    )

@router.get("/mismatches", response_model=list[MismatchOut])
def list_team_mismatches(
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> list[MismatchOut]:
    """
    Answering business question #2, but this time as an HTTP endpoint
    """
    return [
        MismatchOut(
            ticket_id=ticket.id,
            ticket_title=ticket.title,
            assignee_name=assignee.name,
            assignee_team=assignee.team,
            owner_name=owner.name,
            owner_team=owner.team,
        )
        for ticket, document, assignee, owner in service.get_team_mismatches()
    ]

@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(
    ticket_id: int,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> TicketOut:
    ticket = service.get_ticket_by_id(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ticket with id {ticket_id}"
        )
    return TicketOut.model_validate(ticket)