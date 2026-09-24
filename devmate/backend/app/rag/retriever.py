"""
This wraps the already persisted Chroma vector store as a langchain retriever, then
it formats retrieved chunks into a citation-ready context string
"""

from langchain_core.documents import Document as LCDocument

from app.rag.vector_store import load_vector_store

#this constant is used to set the default # of results from the retriever
DEFAULT_K = 4

def get_similarity_retriever(k: int = DEFAULT_K, category: str | None = None):
    """
    Plain nearest-neighbor retrieval - the default search type, ranked purely by 
    closeness to the query. 
    """
    #first, we load up our local vector store
    vector_store = load_vector_store()
    #next, we set up our search parameters (specifically the # of results to return)
    search_kwargs: dict = {"k": k}
    if category is not None:
        search_kwargs["filter"] = {"category": category}
    return vector_store.as_retriever(search_type="similarity", search_kwargs=search_kwargs)

def get_diverse_retriever(k: int = DEFAULT_K, fetch_k: int = 20, lambda_mult: float = 0.5):
    """
    MMR(Maximal Marginal Relevance) retrieval - pulls the 'fetch_k' similarity coordinates first,
    then it re-ranks them to help balance relevance vs diversity, that way all results are not
    all just near-duplicates of the same data. lambda_mult=1.0 behaves like a plain similarity
    search (aka minimum diversity); lower values favor diversity more down to a minimum of 0.0
    (maximum diversity)
    """
    vector_store = load_vector_store()
    return vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": fetch_k, "lambda_mult": lambda_mult}
    )

def format_retrieved_context(documents: list[LCDocument]) -> str:
    """
    this turns retrieved chunks into a single citation-ready string
    """
    return "\n\n".join(
        f"[Source: {document.metadata['title']}]\n{document.page_content}"
        for document in documents
    )
   