"""The Agent Loop — follow the README and fill in each part."""

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)

# Pretend order system. The model has never seen this data.
ORDERS = {
    "A1001": {"status": "shipped", "tracking": "1Z999AA10123456784"},
    "A1002": {"status": "processing", "tracking": None},
}
PACKAGES = {"1Z999AA10123456784": "Out for delivery in Austin, TX"}


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- Part 1: ask without tools ---
banner("Part 1: ask without tools")


# --- Part 2: define a tool and bind it ---
banner("Part 2: define a tool and bind it")


# --- Part 3: run the tool and append the result ---
banner("Part 3: run the tool and append the result")


# --- Part 4: ask again with the history ---
banner("Part 4: ask again with the history")


# --- Part 5: make it a loop ---
banner("Part 5: make it a loop")


# --- Part 6: a second tool ---
banner("Part 6: a second tool")


# --- Part 7: replace the loop with create_agent ---
banner("Part 7: replace the loop with create_agent")
