"""
holds our /documents routes
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import KnowledgeBaseService, get_knowledge_base_service
from app.api.schemas import DocumentOut, StaleDocumentOut, DocumentPage
from app.api.security import require_api_key


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    dependencies=[Depends(require_api_key)]
)

#get documents
@router.get("", response_model=DocumentPage, status_code=status.HTTP_200_OK)
def list_documents(
    #Here, Query() is used to declare query parameters for the endpoint. Skip and limit are both optional
    #parameters to control pagination. ge and le stands for greater than or equal to and less than or equal
    #to respectively.
    skip: int = Query(0, ge=0, description="Number of documents to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max documents to return"),

    #the Depends() function tells FastAPI that this is the dependency injection point
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> DocumentPage:
    """
    model_validate(document) reads id/title/category/... straight off of each plain Document
    object's attributes (from_attributes=True on DocumentOut is what makes this possible)
    """
    all_documents=service.get_all_documents()
    page=all_documents[skip: skip + limit]

    return DocumentPage(
        items=[DocumentOut.model_validate(document) for document in page],
        total=len(all_documents),
        skip=skip,
        limit=limit
    )

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

#Get document by id
@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> DocumentOut:
    document = service.get_document_by_id(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No document with id {document_id}",
        )
    return DocumentOut.model_validate(document)