"""Watching a Model Call Tools — follow the README and fill in each part."""

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- Part 1: define two tools ---


# --- Part 2: see what the model sees ---
banner("Part 2: see what the model sees")


# --- Part 3: bind and watch ---
banner("Part 3: bind and watch")


# --- Part 4: run it and hand back the result ---
banner("Part 4: run it and hand back the result")


# --- Part 5: make it a loop ---
banner("Part 5: make it a loop")


# --- Part 6: break a tool ---
