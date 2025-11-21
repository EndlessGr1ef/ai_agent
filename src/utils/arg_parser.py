"""Argument parsing utilities."""

import argparse
import os


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="LangChain OpenAI-compatible agent with optional RAG (Chroma)"
    )
    parser.add_argument(
        "-s",
        "--system",
        type=str,
        default=os.getenv("OPENAI_SYSTEM_PROMPT", "You are a helpful assistant for software development."),
        help="System prompt (default from env OPENAI_SYSTEM_PROMPT)",
    )
    parser.add_argument(
        "-m",
        "--model",
        type=str,
        default=os.getenv("OPENAI_MODEL", "MiniMax-M2"),
        help="Model name (default from env OPENAI_MODEL or 'MiniMax-M2')",
    )
    parser.add_argument(
        "-u",
        "--base-url",
        type=str,
        default=os.getenv("OPENAI_BASE_URL", "https://api.minimax.io/v1"),
        help="Custom OpenAI-compatible API base_url (default from env OPENAI_BASE_URL)",
    )
    parser.add_argument(
        "-t",
        "--temperature",
        type=float,
        default=0.5,
        help="Sampling temperature (default 0.5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Request timeout in seconds (default: 300)",
    )
    # RAG options
    parser.add_argument(
        "--use-rag",
        action="store_true",
        help="Enable retrieval from Chroma before answering"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=os.getenv("CHROMA_COLLECTION", "md_docs"),
        help="Chroma collection name"
    )
    parser.add_argument(
        "--chroma-host",
        type=str,
        default=os.getenv("CHROMA_HOST", "localhost"),
        help="Chroma server host"
    )
    parser.add_argument(
        "--chroma-port",
        type=int,
        default=int(os.getenv("CHROMA_PORT", "9000")),
        help="Chroma server port (default 9000)"
    )
    # RAG retrieval options
    parser.add_argument(
        "--top-k",
        type=int,
        default=int(os.getenv("TOP_K", "4")),
        help="Number of chunks to retrieve (default 4)"
    )
    parser.add_argument(
        "--embed-model",
        type=str,
        default=os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
        help="Embedding model name"
    )

    # Category filter options
    parser.add_argument(
        "--category",
        type=str,
        help="Filter by category (e.g., 'AI/RAG', 'Backend', 'Frontend')"
    )
    parser.add_argument(
        "--subcategory",
        type=str,
        help="Filter by subcategory (e.g., 'RAG', 'Go', 'Python')"
    )
    parser.add_argument(
        "--topic",
        type=str,
        help="Filter by topic (e.g., '项目技术文档')"
    )
    parser.add_argument(
        "--language",
        type=str,
        help="Filter by programming language (e.g., 'Go', 'Python', 'JavaScript')"
    )

    # Context compression options
    parser.add_argument(
        "--enable-compression",
        action="store_true",
        default=False,
        help="Enable automatic context compression for long conversations"
    )
    parser.add_argument(
        "--disable-compression",
        action="store_true",
        default=False,
        help="Disable automatic context compression (override default)"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=80000,
        help="Maximum token limit for context compression (default: 80000, 80%% of 100K)"
    )

    # Memory options
    parser.add_argument(
        "--session-id",
        type=str,
        help="会话 ID，启用记忆功能"
    )
    parser.add_argument(
        "--memory-collection",
        type=str,
        default="agent_memory",
        help="记忆集合名称（默认: agent_memory）"
    )
    parser.add_argument(
        "--memory-k",
        type=int,
        default=5,
        help="检索历史记忆的数量（默认: 5）"
    )

    return parser.parse_args()

