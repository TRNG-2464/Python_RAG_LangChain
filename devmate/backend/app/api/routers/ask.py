"""
/ask routes - this is our grounded Q & A endpoint
"""

from fastapi import APIRouter, Depends, status

from app.api.schemas import AskRequest, AskResponse, AskStrictRequest, AskConversationRequest
from app.api.security import require_api_key
from app.rag.qa_chain import answer_question, answer_question_strict, ask_with_memory, get_conversation_memory

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

#Day 11 Phase B answer Key
@router.post("/conversation", response_model=AskResponse, status_code=status.HTTP_200_OK)
def ask_conversation(request: AskConversationRequest) -> AskResponse:
    memory = get_conversation_memory(request.conversation_id)
    result = ask_with_memory(memory, request.question)
    return AskResponse(answer=result.answer, sources=result.sources)