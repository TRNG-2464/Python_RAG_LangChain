"""
/ask routes - this is our grounded Q & A endpoint
"""

from fastapi import APIRouter, Depends, status

from app.api.schemas import AskRequest, AskResponse, AskStrictRequest
from app.api.security import require_api_key
from app.rag.qa_chain import answer_question, answer_question_strict

router = APIRouter(
    prefix="/ask",
    tags=["ask"],
    dependencies=[Depends(require_api_key)]
)

@router.post("", response_model=AskResponse, status_code=status.HTTP_200_OK)
def ask(request: AskRequest) -> AskResponse:
    result = answer_question(request.question)
    return AskResponse(answer=result.answer, sources=result.sources)

@router.post("/strict", response_model=AskResponse, status_code=status.HTTP_200_OK)
def ask_strict(request: AskStrictRequest) -> AskResponse:
    result = answer_question_strict(request.question, score_threshold=request.score_threshold)
    return AskResponse(answer=result.answer, sources=result.sources)