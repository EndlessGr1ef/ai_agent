"""LLM configuration utilities."""

import os
import sys

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import anthropic
import chromadb
from chromadb.config import Settings


def require_api_key() -> str:
    """Ensure ANTHROPIC_API_KEY or OPENAI_API_KEY is set; return its value or exit."""
    load_dotenv()
    # Try ANTHROPIC_API_KEY first, fall back to OPENAI_API_KEY for backward compatibility
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print(
            "[Error] ANTHROPIC_API_KEY or OPENAI_API_KEY not found.\n"
            "Please create a .env file at project root and set:\n"
            "ANTHROPIC_API_KEY=your_api_key\n"
        )
        sys.exit(1)
    return api_key


def build_llm(
    api_key: str,
    base_url: str,
    model: str,
    temperature: float = 0.6,
    timeout: int = 30,
    use_anthropic: bool = False
) -> ChatOpenAI | anthropic.Anthropic:
    """Create an LLM instance using either Anthropic SDK or OpenAI-compatible interface.

    Args:
        api_key: API key
        base_url: Base URL for the API
        model: Model name
        temperature: Sampling temperature (0.0-1.0, recommend 1.0 for MiniMax)
        timeout: Request timeout in seconds
        use_anthropic: Whether to use Anthropic SDK (default: False)

    Returns:
        Either ChatOpenAI or Anthropic client
    """
    if use_anthropic or "anthropic" in base_url:
        # Use Anthropic SDK
        return anthropic.Anthropic(
            api_key=api_key,
            base_url=base_url if base_url else None,
        )
    else:
        # Use OpenAI-compatible interface (default)
        return ChatOpenAI(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=temperature,
            request_timeout=timeout,
        )


def build_anthropic_llm(
    api_key: str,
    base_url: str | None = None,
    model: str = "MiniMax-M2",
    temperature: float = 1.0,
    timeout: int = 30
) -> anthropic.Anthropic:
    """Create an Anthropic client for MiniMax API.

    Args:
        api_key: API key
        base_url: Base URL (defaults to MiniMax Anthropic endpoint)
        model: Model name (default: MiniMax-M2)
        temperature: Sampling temperature (0.0-1.0, recommend 1.0 for MiniMax)
        timeout: Request timeout in seconds

    Returns:
        Anthropic client
    """
    # Default to MiniMax Anthropic endpoint
    if not base_url:
        # Use Chinese endpoint by default, can be changed via environment variable
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")

    return anthropic.Anthropic(
        api_key=api_key,
        base_url=base_url,
    )


def create_chroma_client(host: str, port: int) -> chromadb.HttpClient:
    """Create Chroma HTTP client."""
    settings = Settings(allow_reset=True, anonymized_telemetry=False)
    return chromadb.HttpClient(host=host, port=port, settings=settings)
