"""
Day 8 playground: two small throwaway checks that build intuition before the real work begins.
an example of the text splitter, and what an embedding actually looks like

run from /backend directory using:
    python -m scripts.day8_playground
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_ollama import OllamaEmbeddings

EMBEDDING_MODEL = "nomic-embed-text"

def demo_splitter_mechanics() -> None:
    splitter = RecursiveCharacterTextSplitter(chunk_size=70, chunk_overlap=10)

    text = (
        "Paragraph one covers onboarding steps for new engineers. \n\n"
        "Paragraph two covers on-call escalation procedures for incidents. \n\n"
        "Paragraph three covers the deployment details in order."
    )

    chunks = splitter.split_text(text)
    for i, chunk in enumerate(chunks, start=1):
        print(f"--- Chunk {i} ({len(chunk)} chars)---")
        print(chunk)

def demo_embedding_shape()-> None:
    embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)
    vector = embeddings.embed_query("How do I roll back a failed deploy?")
    print(f"Vector Length: {len(vector)}")
    print(f"First 5 values: {vector[:5]}")

def main() -> None:
    print("=== RecursiveCharacterTextSplitter mechanics ===")
    demo_splitter_mechanics()

    print("\n=== OllamaEmbeddings shape check ===")
    demo_embedding_shape()

if __name__ == "__main__":
    main()