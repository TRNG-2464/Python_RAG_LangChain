"""
holds our /tickets routes
"""

from fastapi import APIRouter, Depends

from app.api.deps import KnowledgeBaseService, get_knowledge_base_service
from app.api.schemas import MismatchOut, TicketOut
from app.api.security import require_api_key

router = APIRouter(
    prefix="/tickets",
    tags=["tickets"],
    dependencies=[Depends(require_api_key)]
)

@router.get("", response_model=list[TicketOut])
def list_tickets(
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> list[TicketOut]:
    return [TicketOut.model_validate(ticket) for ticket in service.get_all_tickets()]

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