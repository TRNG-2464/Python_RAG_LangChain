"""A LangGraph Graph with State — follow the README and fill in each part."""

from typing import Annotated

from langchain_core.messages import AnyMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

llm = ChatOllama(model="llama3.1", temperature=0)

# Pretend data sources. The model has never seen these.
WEATHER = {"Lisbon": "22C and sunny", "Oslo": "4C and snowing"}
RATES = {("USD", "EUR"): 0.92, ("EUR", "USD"): 1.09}


@tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    return WEATHER.get(city, f"No weather data for {city}")


@tool
def convert_currency(amount: float, from_currency: str, to_currency: str) -> str:
    """Convert an amount of money between currencies, using three-letter codes like 'USD' or 'EUR'."""
    rate = RATES.get((from_currency.upper(), to_currency.upper()))
    if rate is None:
        return f"No rate for {from_currency} to {to_currency}"
    return f"{amount} {from_currency} = {round(amount * rate, 2)} {to_currency}"


tools = [get_weather, convert_currency]
tools_by_name = {t.name: t for t in tools}
llm_with_tools = llm.bind_tools(tools)


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- Part 1: the state schema ---


# --- Part 2: a one-node graph ---
banner("Part 2: a one-node graph")


# --- Part 3: a tool node ---
banner("Part 3: a tool node")


# --- Part 4: a conditional edge ---
banner("Part 4: a conditional edge")


# --- Part 5: close the cycle ---
banner("Part 5: close the cycle")


# --- Part 6: swap the reducer ---
