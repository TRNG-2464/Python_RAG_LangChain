"""From Files to a Vector Store — follow the README and fill in each part.

Run this from the lab directory (not from src/) so the data/ paths resolve.
"""

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_ollama import OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

embeddings = OllamaEmbeddings(model="nomic-embed-text")


# --- Part 1: load a file ---


# --- Part 2: load both files and add metadata ---


# --- Part 3: split into chunks ---


# --- Part 4: watch the parameters ---


# --- Part 5: embed and store ---


# --- Part 6: search it ---
