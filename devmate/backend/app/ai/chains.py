"""
Langchain Fundamentals: one prompt-template-and-chain pattern, reused for Ticket summaries
today, and document descriptions in our challenge.

Nothing in this document talks to FastAPI, KnowledgeBaseService, or any other part of the app,
- following separation of concerns principle
"""
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_ollama import ChatOllama

from app.models import Document

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

_document_description_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are Devmate, an internal engineering assistant for Northbeam."
        "Write exactly one plain English sentence describing the given document -"
        "what it covers, and whether it looks due for review given how long it's been"
        "since its last review. Do not invent details that aren't provided."
    ),
    (
        "human",
        "Title: {title}\nCategory: {category}\n"
        "Days since last reviewed: {days_since_reviewed}",
    ),
])

document_description_chain = _document_description_prompt | _llm | StrOutputParser()

def describe_document(title: str, category: str, days_since_reviewed: int) -> str:
    return document_description_chain.invoke({
        "title": title,
        "category": category,
        "days_since_reviewed": days_since_reviewed
    })


"""
Our first example of a chain with a structured output parser, which returns a structured
object, instead of just a string
"""
class TicketTriageSuggestion(BaseModel):

    """
    A typed suggestion, not a sentence - the point of structured output. Deliberately built only
    from a ticket's title and status, witholding its recorded priority, so this is DevMate's own
    independent read on urgency, not just an echo of the value it is handed.
    """
    suggested_priority: str = Field(
        description="DevMate's own priority guess: one of Low, Medium, High, Critical"
    )
    needs_escalation: bool = Field(
        description="True if this looks urgent enough to escalate immediately"
    )
    reasoning: str = Field(
        description="One sentence explaining the suggestion, referencing only"
        " the title and status given - not the ticket's actual recorded priority"
    )

_ticket_triage_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are DevMate, an internal engineering assistant for Northbeam. "
        "Given only a ticket's title and status - not its recorded priority, "
        "suggest what priority it should have and whether it needs escalation."
        " Do not invent details that are not provided."
    ),
    (
        "human",
        "Title: {title}\nStatus: {status}",
    )
])

#.with_structured_output comes from the chatollama package to allow structured ouptut
ticket_triage_chain = _ticket_triage_prompt | _llm.with_structured_output(TicketTriageSuggestion)

def suggest_ticket_triage(title: str, status: str) -> TicketTriageSuggestion:
    return ticket_triage_chain.invoke({"title": title, "status": status})

##Next, we can structure our follow-up prompt and chain

_ticket_followup_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are DevMate, an internal engineering assistant for Northbeam, "
        "answering follow-up questions about hte ticket below. Use the "
        "conversation history to answer without asking the engineer to "
        "repeat information already given. Do not invent details that aren't"
        " provided. \n\nTicket: {ticket_context}"
    ),
    
    MessagesPlaceholder("history"),
    ("human", "{question}"),
    
])

ticket_followup_chain = _ticket_followup_prompt | _llm | StrOutputParser()

def ask_ticket_followup(ticket_context: str, history: list, question: str) -> str:
    """
    'history' is a plain list of BaseMessage objects (HumanMessage/AIMessage) that
    the CALLER owns and appends to after every turn. The function itself is stateless;
    it doesn't persist anything between calls.
    """
    return ticket_followup_chain.invoke({
        "ticket_context": ticket_context,
        "history": history,
        "question": question,
    })

"""
the @tool decorator wraps a function with a schema that the model can then use to call it,
and to validate the function's output. This tool will look up a document by its id and return
its title and category, which the model can then use to answer a question about a ticket that
references that document.
"""
@tool
def look_up_related_document(document_id: int) -> str:
    """Look up Northbeam document by id and return its title and category"""
    document = Document.find_by_id(document_id)
    if document is None:
        return f"No document found with id {document_id}."
    return f"Document {document_id}: '{document.title}' ({document.category.value})"

"""
this is a second, bound variant of the same shared _llm - not a second
ChatOllama instance. bind_tools(...) wraps the _llm with the tool's schema attached
so that the model can choose to request and call it.
"""
_llm_with_tools = _llm.bind_tools([look_up_related_document])

def ask_about_ticket_document(
        title: str, related_document_id: int | None, question: str
) -> str:
    """
    A single-step tool-calling loop: the model decides whether it needs to call
    the look_up_related_document tool to answer 'question', and if so, the tool's
    results are fed back into it for one final answer.
    """
    messages = [
        SystemMessage(
            content=(
                "You are DevMate, an internal engineering assistant for Northbeam. " 
                "You have a tool to look up a ticket's related document by id when you " 
                "need its title or category to answer a question. Do not invent details" 
                "that aren't provided or returned by the tool."
            )
        ),
        HumanMessage(
            content=(
                f"Ticket: {title}, (related_document_id={related_document_id}). "
                f"{question}"
            )
        )
    ]

    ai_message = _llm_with_tools.invoke(messages)
    messages.append(ai_message)

    for tool_call in ai_message.tool_calls:
        tool_result = look_up_related_document.invoke(tool_call)
        messages.append(tool_result)

    if ai_message.tool_calls:
        ai_message = _llm_with_tools.invoke(messages)

    return ai_message.content