"""Retrieval and Grounded Answers — follow the README and fill in each part."""

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

embeddings = OllamaEmbeddings(model="nomic-embed-text")
llm = ChatOllama(model="llama3.1", temperature=0)

CORPUS = [
    Document(
        page_content=(
            "Employees accrue 15 days of paid time off each year, credited "
            "monthly at 1.25 days per month. Up to 10 unused days may carry "
            "into the following year; anything beyond that is forfeited. "
            "Time off requests must be submitted at least 14 days in advance."
        ),
        metadata={"source": "pto.txt", "topic": "time-off"},
    ),
    Document(
        page_content=(
            "Sick leave is separate from paid time off. Employees receive 8 "
            "sick days per year. Sick days do not carry over and are not paid "
            "out on departure. A physician's note is required for any absence "
            "longer than three consecutive days."
        ),
        metadata={"source": "sick.txt", "topic": "time-off"},
    ),
    Document(
        page_content=(
            "Expense reports are due by the 5th of each month for the previous "
            "month. Reports submitted after the 10th are held until the next "
            "cycle. Itemized receipts are required for every expense over 25 "
            "dollars. Reimbursement is issued within 21 days of approval."
        ),
        metadata={"source": "expenses.txt", "topic": "expenses"},
    ),
    Document(
        page_content=(
            "Air travel must be booked at least 21 days before departure. "
            "Economy class is standard for all flights under six hours. Hotel "
            "stays are capped at 200 dollars per night excluding tax, and "
            "meals are reimbursed up to 60 dollars per day."
        ),
        metadata={"source": "travel.txt", "topic": "expenses"},
    ),
]


# --- Part 1: build a store ---


# --- Part 2: vary k ---


# --- Part 3: add diversity with MMR ---


# --- Part 4: filter by metadata ---


# --- Part 5: format the chunks with their sources ---


# --- Part 6: write the grounding prompt ---


# --- Part 7: ask something the corpus can't answer ---


# --- Part 8: return the sources too ---
