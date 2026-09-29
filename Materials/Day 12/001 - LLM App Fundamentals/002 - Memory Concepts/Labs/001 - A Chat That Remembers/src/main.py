"""A Chat That Remembers — follow the README and fill in each part."""

from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from langchain_ollama import ChatOllama

llm = ChatOllama(model="llama3.1", temperature=0)


# --- Part 5 setup: the trimmer ---


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- Part 1: watch it forget ---
banner("Part 1: watch it forget")


# --- Part 2: keep the list ourselves ---
banner("Part 2: keep the list ourselves")


# --- Part 3: look at what's being sent ---
banner("Part 3: look at what's being sent")


# --- Part 4: a chat loop ---
banner("Part 4: a chat loop")


# --- Part 5: trim the history ---
banner("Part 5: trim the history")


# --- Part 6: summarize instead ---
banner("Part 6: summarize instead")
