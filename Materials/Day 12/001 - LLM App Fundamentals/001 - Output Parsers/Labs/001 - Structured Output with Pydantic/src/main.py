"""Structured Output with Pydantic — follow the README and fill in each part."""

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

llm = ChatOllama(model="llama3.1", temperature=0)


def banner(title):
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# --- Part 1: a plain call, no structure ---
banner("Part 1: a plain call, no structure")


# --- Part 2: describe the shape ---


# --- Part 3: prompt and parse ---
banner("Part 3: prompt and parse")


# --- Part 4: native structured output ---
banner("Part 4: native structured output")


# --- Part 5: watch validation fail ---
banner("Part 5: watch validation fail")


# --- Part 6: get a list back ---
banner("Part 6: get a list back")
