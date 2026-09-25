"""
This demonstrates the second half of RAG: takes a retrievers output and actually answers
the question with it, grounded in the retrieved context, with citations back to the
documents that the context came from.

"""

from dataclasses import dataclass

from langchain_core.documents import Document as LCDocument
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from app.rag.retriever import (
    DEFAULT_K,
    format_retrieved_context,
    get_similarity_retriever,
    get_threshold_retriever
)

#set up our chatollama instance
_llm = ChatOllama(
    model="llama3.2",
    base_url="http://localhost:11434",
    temperature=0.0
)

_rag_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are DevMate, an internal engineering assistant for Northbeam."
        "Answer the engineer's question using ONLY the context below - "
        "do not use any outside knowledge, and do not invent details that"
        "aren't in the context. If the context doesn't contain enough"
        "information to answer the question, say so plainly instead of"
        "guessing. \n\nContext:\n{context}",
    ),
    (
        "human", "{question}",
    )
])

rag_answer_chain = _rag_prompt | _llm | StrOutputParser()

@dataclass
class AskResult:
    """
    what our answer_question() and answer_question_strict() both return -
    the API layer turns this into anAskResponse, but this class itself
    knows nothing about the FastAPI or Pydantic setup.
    """
    answer: str
    sources: list[str]

def _citation_titles(documents: list[LCDocument]) -> list[str]:
    """
    Document titles, in first-seen order, with duplicates dropped. Never
    return two chunks from the same document, but in the case of a larger
    db, it eventually will, and a citation list is more useful to an engineer
    without the same source being listed three times.
    """
    seen: set[str] = set()
    titles: list[str] = []
    for document in documents:
        title = document.metadata["title"]
        if title not in seen:
            seen.add(title)
            titles.append(title)
    return titles

def answer_question(question: str, k: int = DEFAULT_K) -> AskResult:
    """
    The full RAG path: retreive, format, generate, cite. Always calls the llm,
    even if the retrieved context turns out to be a weak match(because we are using
    the get_similarity_retriever)
    """
    retriever = get_similarity_retriever(k=k)
    documents = retriever.invoke(question)
    context = format_retrieved_context(documents)
    answer = rag_answer_chain.invoke({"context": context, "question": question})
    return AskResult(answer=answer, sources=_citation_titles(documents))


#PHASE B STUDENT CHALLENGE
NOT_CONFIDENT_ANSWER = (
    "I don't have enough confidence in Northbeam's documents to answer that question. " \
    "Try rephrasing it, or check with the relevant team directly. "
)

def answer_question_strict(question: str, score_threshold: float, k: int = DEFAULT_K) -> AskResult:
    retriever = get_threshold_retriever(score_threshold=score_threshold, k=k)
    documents = retriever.invoke(question)
    if not documents:
        return AskResult(answer=NOT_CONFIDENT_ANSWER, sources=[])
    context = format_retrieved_context(documents)
    answer = rag_answer_chain.invoke({"context": context, "question": question})
    return AskResult(answer=answer, sources=_citation_titles(documents))