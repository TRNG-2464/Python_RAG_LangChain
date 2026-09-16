"""
holds our /documents routes
"""

from fastapi import APIRouter, Depends

from app.api.deps import KnowledgeBaseService, get_knowledge_base_service
from app.api.schemas import DocumentOut, StaleDocumentOut
from app.api.security import require_api_key


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_api_key)]
)

#get documents
@router.get("", response_model=list[DocumentOut])
def list_documents(
    #the Depends() function telsl FastAPI that this is the dependency injection point
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> list[DocumentOut]:
    """
    model_validate(document) reads id/title/category/... straight off of each plain Document
    object's attributes (from_attributes=True on DocumentOut is what makes this possible)
    """
    return [DocumentOut.model_validate(document) for document in service.get_all_documents()]

#get stale documents
@router.get("/stale", response_model=list[StaleDocumentOut])
def list_stale_documents(
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> list[StaleDocumentOut]:
    """
    This answers business question #1 again, but as an HTTP endpoint
    """
    return [
        StaleDocumentOut(
            id=document.id,
            title=document.title,
            category=document.category,
            days_since_last_reviewed=document.days_since_last_reviewed(),
        )
        for document in service.get_stale_documents(threshold=90)
    ]