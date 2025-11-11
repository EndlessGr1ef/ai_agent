"""Main entry point for the LLM agent."""

import sys
from pathlib import Path

# Add src directory to Python path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from config.llm_config import build_llm, require_api_key
from config.retriever import build_retriever
from agents import ChatAgent, RagAgent
from utils.arg_parser import parse_args


def main() -> None:
    """Main entry point."""
    # Parse command line arguments
    args = parse_args()

    # Get API key
    api_key = require_api_key()

    # Build LLM
    llm = build_llm(
        api_key=api_key,
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
        timeout=args.timeout,
    )

    # Initialize context compressor
    compressor = None
    # Enable compression by default, unless explicitly disabled by user
    if not args.disable_compression:
        args.enable_compression = True

    if args.enable_compression:
        try:
            from context_compressor import create_compressor
            compressor = create_compressor(max_tokens=args.max_tokens)
            print(f"✓ Context compression enabled (max tokens: {args.max_tokens})")
        except ImportError:
            print("⚠️  Context compression requested but compressor not available")
            print("   Install with: pip install transformers")

    # Choose and run the appropriate agent
    if args.use_rag:
        try:
            retriever = build_retriever(
                collection_name=args.collection,
                host=args.chroma_host,
                port=args.chroma_port,
                embed_model_name=args.embed_model,
                top_k=args.top_k,
                category_filter=args.category,
                subcategory_filter=args.subcategory,
                topic_filter=args.topic,
                language_filter=args.language,
            )
        except Exception as e:
            print(f"[Error] Failed to initialize retriever: {e}")
            print("[Info] Falling back to normal chat mode.")
            # Fallback to chat mode
            agent = ChatAgent(
                llm=llm,
                system_prompt=args.system,
                compressor=compressor,
                enable_compression=args.enable_compression
            )
            agent.run()
            return

        # Print active filters
        if any([args.category, args.subcategory, args.topic, args.language]):
            print("\n" + "="*60)
            print("Active Filters:")
            if args.category:
                print(f"  Category: {args.category}")
            if args.subcategory:
                print(f"  Subcategory: {args.subcategory}")
            if args.topic:
                print(f"  Topic: {args.topic}")
            if args.language:
                print(f"  Language: {args.language}")
            print("="*60 + "\n")

        # Run RAG agent
        agent = RagAgent(
            llm=llm,
            retriever=retriever,
            system_prompt=args.system,
            compressor=compressor,
            enable_compression=args.enable_compression
        )
        agent.run()
    else:
        # Run chat agent
        agent = ChatAgent(
            llm=llm,
            system_prompt=args.system,
            compressor=compressor,
            enable_compression=args.enable_compression
        )
        agent.run()


if __name__ == "__main__":
    main()
