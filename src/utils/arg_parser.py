"""Argument parsing utilities."""

import argparse
import os


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="LLM agent with optional RAG (Chroma) - Supports OpenAI-compatible and Anthropic SDK"
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
        default=os.getenv("OPENAI_BASE_URL", os.getenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")),
        help="Custom API base_url (default from env OPENAI_BASE_URL or ANTHROPIC_BASE_URL)",
    )
    parser.add_argument(
        "-t",
        "--temperature",
        type=float,
        default=float(os.getenv("OPENAI_TEMPERATURE", os.getenv("ANTHROPIC_TEMPERATURE", "1.0"))),
        help="Sampling temperature (default from env OPENAI_TEMPERATURE or ANTHROPIC_TEMPERATURE or 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("REQUEST_TIMEOUT", "300")),
        help="Request timeout in seconds (default from env REQUEST_TIMEOUT or 300)",
    )
    parser.add_argument(
        "--use-anthropic",
        action="store_true",
        default=os.getenv("USE_ANTHROPIC", "false").lower() == "true",
        help="Use Anthropic SDK instead of OpenAI-compatible interface (default from env USE_ANTHROPIC or false)",
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
        default=int(os.getenv("MAX_TOKENS", "80000")),
        help="Maximum token limit for context compression (default from env MAX_TOKENS or 80000)"
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
        default=os.getenv("MEMORY_COLLECTION", "agent_memory"),
        help="记忆集合名称（default from env MEMORY_COLLECTION or agent_memory）"
    )
    parser.add_argument(
        "--memory-k",
        type=int,
        default=int(os.getenv("MEMORY_K", "5")),
        help="检索历史记忆的数量（default from env MEMORY_K or 5）"
    )

    # Dual output (JSON format) options
    parser.add_argument(
        "--disable-dual-output",
        action="store_true",
        default=False,
        help="禁用 JSON 双输出格式（摘要+内容）"
    )

    # Thinking process display options
    parser.add_argument(
        "--show-thinking",
        action="store_true",
        default=False,
        help="默认显示思考过程"
    )
    parser.add_argument(
        "--hide-thinking",
        action="store_true",
        default=False,
        help="默认隐藏思考过程"
    )
    
    # Scraping options
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="Enable web scraping mode"
    )
    parser.add_argument(
        "--scrape-url",
        type=str,
        help="URL to scrape"
    )
    parser.add_argument(
        "--scraper-type", 
        type=str,
        default="default",
        choices=["default", "prts", "prts_wiki"],
        help="Type of scraper to use"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to scrape"
    )
    parser.add_argument(
        "--scrape-output-dir",
        type=str,
        default="scraped_content",
        help="Directory to save scraped content"
    )
    parser.add_argument(
        "--no-js-render",
        action="store_true",
        help="Disable JavaScript rendering for scraping"
    )
    parser.add_argument(
        "--scrape-only",
        action="store_true", 
        help="Only scrape content, don't ingest to ChromaDB"
    )

    return parser.parse_args()

