"""
This demonstrates the second half of RAG: takes a retrievers output and actually answers
the question with it, grounded in the retrieved context, with citations back to the
documents that the context came from.

"""

from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnablePassthrough
from langchain_core.documents import Document as LCDocument
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
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


#Day 11 Retrieval chain start here

_reg_prompt_with_history = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are DevMate, an internal engineering assistant for Northbeam."
        "Answer the engineer's question using ONLY the context below - do not "
        "use any outside knowledge, and do not invent details that aren't in "
        "the context. If the context doesn't contain enough infomration to "
        "answer the question, say so plainly instead of guessing. \n\n{context}\n\n"
        "Summary of the conversation so far (empty if this is the first question): {summary}"
    ),
    MessagesPlaceholder("recent_turns"),
    ("human", "{question}")
])

rag_answer_chain_with_history = _reg_prompt_with_history | _llm | StrOutputParser()

def _retrieve(input_dict: dict) -> list[LCDocument]:
    """
    This rebuilds the retriever fresh on every call via the get_similarity_retriever
    - never a retriever that is captured once and then reused. This takes the whole 
    accumulated dict rather than just a bare question string because that is what 
    RunnablePassthrough() is going to need to pass in every step.
    """
    retriever = get_similarity_retriever(k=DEFAULT_K)
    return retriever.invoke(input_dict["question"])


"""
This is our formal retrieval chain: one composed Runnable replacing what the answer_question does but
as three seperately-invoked plain Python statements. RunnablePassthrough.assign(...) merges a new key
into the existing input_dict on each step - documents, then context, then finally the answer - so that every
later step can see everything the earlier steps produced. Each value that is passed to .assign() here 
is a plain Python callable or an existing Runnable; Context = lambda is actuall a function that takes 
the current input and returns the value for 'context'
"""
retrieval_chain = (
    RunnablePassthrough.assign(documents=_retrieve)
    | RunnablePassthrough.assign(context=lambda x: format_retrieved_context(x["documents"]))
    | RunnablePassthrough.assign(answer=rag_answer_chain_with_history)
)

@dataclass
class ConversationMemory:
    """
    this is caller-owned conversation data
    """
    summary: str = ""
    recent_messages: list[BaseMessage] = field(default_factory=list)


MAX_RECENT_MESSAGES = 4

_summary_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Summarize the conversation turns below in 2-3 sentences, preserving "
        "anything factual an engineer would need to answer a follow-up question. "
        "If an existing summary is given, build on it rather than starting over from"
        " nothing. Write only the summary itself - do not mention whether a summary "
        "already exists or comment on these instructions. \n\n Existing summary (empty "
        "if there isn't one yet): {existing_summary}",
    ),
    MessagesPlaceholder("turns_to_summarize"),
    ("human", "Summarize the conversation above, following the instructions given.")
])

summarization_chain = _summary_prompt | _llm | StrOutputParser()

def record_turn(memory: ConversationMemory, question: str, answer: str) -> None:
    """
    This appends this turn's messages to the memory.recent_messages list, then folds
    the oldest overflow into memory.summary once more than MAX_RECENT_MESSAGES has
    accumulated.
    """
    memory.recent_messages.append(HumanMessage(content=question))
    memory.recent_messages.append(AIMessage(content=answer))

    if len(memory.recent_messages) > MAX_RECENT_MESSAGES:
        overflow = memory.recent_messages[:-MAX_RECENT_MESSAGES]
        memory.recent_messages = memory.recent_messages[-MAX_RECENT_MESSAGES:]
        memory.summary = summarization_chain.invoke({
            "existing_summary": memory.summary,
            "turns_to_summarize": overflow,
        })

def ask_with_memory(memory: ConversationMemory, question: str) -> AskResult:
    """
    This is the memory-aware sibling of answer_question: runs the retrieval_chain
    with this conversation's summary and recent raw turns folded into the prompt, then
    it records the new turn, updating memory.summary if that push crosses the 
    MAX_RECENT_MESSAGES threshold before returning.
    """
    result = retrieval_chain.invoke({
        "question": question,
        "summary": memory.summary,
        "recent_turns": memory.recent_messages,
    })
    record_turn(memory, question, result["answer"])
    return AskResult(answer=result["answer"], sources=_citation_titles(result["documents"]))