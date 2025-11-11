"""LLM configuration utilities."""

import os
import sys

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import chromadb
from chromadb.config import Settings


def require_api_key() -> str:
    """Ensure OPENAI_API_KEY is set; return its value or exit."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(
            "[Error] OPENAI_API_KEY not found.\n"
            "Please create a .env file at project root and set:\n"
            "OPENAI_API_KEY=your_api_key\n"
        )
        sys.exit(1)
    return api_key


def build_llm(
    api_key: str,
    base_url: str,
    model: str,
    temperature: float = 0.6
) -> ChatOpenAI:
    """Create a ChatOpenAI instance with custom base_url and model."""
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
    )


def create_chroma_client(host: str, port: int) -> chromadb.HttpClient:
    """Create Chroma HTTP client."""
    settings = Settings(allow_reset=True, anonymized_telemetry=False)
    return chromadb.HttpClient(host=host, port=port, settings=settings)
