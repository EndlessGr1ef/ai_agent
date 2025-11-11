"""Retriever configuration utilities."""

from config.embeddings import build_embeddings
from config.llm_config import create_chroma_client
from langchain_chroma import Chroma


def build_retriever(
    collection_name: str,
    host: str,
    port: int,
    embed_model_name: str | None = None,
    top_k: int = 4,
    category_filter: str | None = None,
    subcategory_filter: str | None = None,
    topic_filter: str | None = None,
    language_filter: str | None = None
):
    """
    Create a retriever backed by Chroma collection with optional category filters.

    Args:
        collection_name: Chroma collection name
        host: Chroma server host
        port: Chroma server port
        embed_model_name: Embedding model name
        top_k: Number of chunks to retrieve
        category_filter: Filter by category (e.g., "AI/RAG", "Backend")
        subcategory_filter: Filter by subcategory (e.g., "RAG", "Go")
        topic_filter: Filter by topic
        language_filter: Filter by programming language
    """
    embeddings = build_embeddings(embed_model_name)
    client = create_chroma_client(host, port)
    vs = Chroma(
        embedding_function=embeddings,
        collection_name=collection_name,
        client=client,
    )

    # Build filter dictionary
    filter_dict = {}
    if category_filter:
        filter_dict["category"] = category_filter
    if subcategory_filter:
        filter_dict["subcategory"] = subcategory_filter
    if topic_filter:
        filter_dict["topic"] = topic_filter
    if language_filter:
        filter_dict["languages"] = {"$contains": language_filter}

    search_kwargs = {"k": top_k}
    if filter_dict:
        search_kwargs["filter"] = filter_dict

    return vs.as_retriever(search_kwargs=search_kwargs)
