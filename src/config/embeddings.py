"""Embedding model configuration."""

import os

from langchain_huggingface import HuggingFaceEmbeddings


def build_embeddings(model_name: str | None = None) -> HuggingFaceEmbeddings:
    """Create a local embedding model (CPU-friendly)."""
    if not model_name:
        model_name = os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(model_name=model_name)
