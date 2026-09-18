"""
/analytics routes
"""

from fastapi import APIRouter, Depends

from app.api.deps import KnowledgeBaseService, get_knowledge_base_service
from app.api.schemas import WorkloadReport
from app.api.security import require_api_key

router = APIRouter(
    prefix="/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_api_key)]
)

@router.get("/workload", response_model=WorkloadReport)
def get_team_workload(
    service: KnowledgeBaseService = Depends(get_knowledge_base_service)
) -> WorkloadReport:
    report = service.get_team_workload_report()
    """
    compute_team_workload() returns a plain dict shaped to match WorkloadReport schema,
    it gets unpacked using **, this is because it needs to be used for the whole nested report
    instead of just one flat object
    """
    return WorkloadReport(**report)

