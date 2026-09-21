"""
Langchain Fundamentals: one prompt-template-and-chain pattern, reused for Ticket summaries
today, and document descriptions in our challenge.

Nothing in this document talks to FastAPI, KnowledgeBaseService, or any other part of the app,
- following separation of concerns principle
"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

"""
Once shared ChatOllama instance for this entire module - every chain below it
reuses it rather than constructing its own. base_url is spelled out explicitly even
though it matches Ollama's own default, to it is obvious at a glance where this is actually
talking to.
"""
_llm = ChatOllama(
    model="llama3.2",
    base_url="http://localhost:11434",
    temperature=0.2
)

"""
chatprompttemplate - formats a list of messages. In this instance, a system message setting 
the model's role and rules, and a human message carrying the actual request itself. title,
priority, and status as placeholders that filled out further down the chain
"""
_ticket_summary_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are DevMate, an internal engineering assistant for"
        "Northbeam. Summarize the given ticket in exactly one plain"
        "English sentence, written for an engineer skimming a long"
        "list. Do not invent details that aren't provided."
    ),
    (
        "human",
        "Title: {title}\nPriority: {priority}\nStatus: {status}",
    ),
])

"""
LCEL(LangChain Expression Language): 3 independent and swappable pieces - a prompt template,
a chat model, an output parser - composed with '|' into one callable pipeline. This is the line
that you can change to communicate with a different llm
"""
ticket_summary_chain = _ticket_summary_prompt | _llm | StrOutputParser()

def summarize_tickets(title: str, priority: str, status: str) -> str:
    #this is a thin, testable wrapper - entry point for other code calls
    return ticket_summary_chain.invoke({
        "title": title,
        "priority": priority,
        "status": status
    })