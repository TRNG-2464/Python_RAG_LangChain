"""Interrupting for Approval — follow the README and fill in each part."""

from typing import Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import Command, interrupt

llm = ChatOllama(model="llama3.1", temperature=0)

# A pretend support queue. close_ticket really changes it.
TICKETS = {
    "T-101": {"title": "Printer on floor 3 is jammed", "status": "open"},
    "T-102": {"title": "VPN drops every hour", "status": "open"},
    "T-103": {"title": "Request new monitor", "status": "open"},
}


@tool
def list_tickets() -> str:
    """List every support ticket with its id, title, and status."""
    return "\n".join(f"{tid}: {t['title']} [{t['status']}]" for tid, t in TICKETS.items())


@tool
def close_ticket(ticket_id: str) -> str:
    """Close a support ticket by its id (e.g. 'T-101')."""
    if ticket_id not in TICKETS:
        return f"No ticket {ticket_id}"
    TICKETS[ticket_id]["status"] = "closed"
    return f"Closed {ticket_id}"


tools = [list_tickets, close_ticket]
llm_with_tools = llm.bind_tools(tools)
SYSTEM = SystemMessage("You manage the IT support queue. Use the tools; never guess a ticket's status.")


def call_model(state: MessagesState) -> dict:
    return {"messages": [llm_with_tools.invoke([SYSTEM] + state["messages"])]}


def statuses():
    return {tid: t["status"] for tid, t in TICKETS.items()}


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- The graph (Parts 2 and 3 edit this) ---
builder = StateGraph(MessagesState)
builder.add_node("agent", call_model)
builder.add_node("tools", ToolNode(tools))
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", tools_condition)
builder.add_edge("tools", "agent")
graph = builder.compile()


# --- Part 1: watch it act ---
banner("Part 1: watch it act")


# --- Part 4: inspect the paused state ---
banner("Part 4: inspect the paused state")


# --- Part 5: approve ---
banner("Part 5: approve")


# --- Part 6: reject ---
banner("Part 6: reject")


# --- Part 7: a second thread ---
banner("Part 7: a second thread")
