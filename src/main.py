"""Main entry point for the LLM agent."""

import sys
import os
from pathlib import Path

# 重要：在导入任何 Hugging Face 相关库之前设置环境变量
# 设置 Hugging Face 镜像源（解决网络问题）
HF_ENDPOINT = os.getenv('HF_ENDPOINT') or 'https://hf-mirror.com'
os.environ['HF_ENDPOINT'] = HF_ENDPOINT
os.environ['HF_HOME'] = os.path.expanduser('~/.cache/huggingface')
os.environ['HF_HUB_DOWNLOAD_TIMEOUT'] = '300'

# 解决 HuggingFace tokenizers 并行处理警告
os.environ['TOKENIZERS_PARALLELISM'] = 'false'
os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = '1'

# Add src directory to Python path
src_path = Path(__file__).parent
sys.path.insert(0, str(src_path))

from config.llm_config import build_llm, require_api_key
from config.retriever import build_retriever
from agents import RagAgent
from utils.arg_parser import parse_args


def main() -> None:
    """Main entry point."""
    # Parse command line arguments
    args = parse_args()

    # Get API key
    api_key = require_api_key()

    # Determine if we should use Anthropic SDK
    use_anthropic = args.use_anthropic or "anthropic" in args.base_url

    # Build LLM
    if use_anthropic:
        # Use build_llm with use_anthropic flag
        llm = build_llm(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            temperature=args.temperature,
            timeout=args.timeout,
            use_anthropic=True
        )
        print(f"✓ Using Anthropic SDK")
    else:
        # Use OpenAI-compatible interface
        llm = build_llm(
            api_key=api_key,
            base_url=args.base_url,
            model=args.model,
            temperature=args.temperature,
            timeout=args.timeout,
            use_anthropic=False
        )
        print(f"✓ Using OpenAI-compatible interface")

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

    # Initialize memory manager if session_id is provided
    memory_manager = None
    if args.session_id:
        try:
            from utils.memory_manager import MemoryManager
            from config import get_global_embeddings
            
            embeddings = get_global_embeddings(model_name=args.embed_model)
            chroma_client = None
            
            # Create Chroma client (will be used for memory)
            from config.llm_config import create_chroma_client
            chroma_client = create_chroma_client(args.chroma_host, args.chroma_port)
            
            memory_manager = MemoryManager(
                chroma_client=chroma_client,
                collection_name=args.memory_collection,
                embeddings=embeddings
            )
            print(f"✓ Memory enabled (session: {args.session_id}, collection: {args.memory_collection})")
        except Exception as e:
            print(f"⚠️  Failed to initialize memory manager: {e}")
            print("   Continuing without memory functionality")

    # Determine thinking display mode from command line args
    show_thinking = args.show_thinking and not args.hide_thinking

    # Initialize retriever
    retriever = None
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
        print(f"[WARN] 罗德岛数据库连接受限: {e}")
        print("[INFO] PRTS 将进入离线模式运行。")

    # Print active filters if retriever is active
    if retriever and any([args.category, args.subcategory, args.topic, args.language]):
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

    # Run RAG agent with PRTS mode
    use_dual_output = True
    
    # Determine system prompt: use None to enable default PRTS prompt
    # unless user explicitly specified a custom prompt via -s or env var
    default_prompt = "You are a helpful assistant for software development."
    system_prompt = None if args.system == default_prompt else args.system
    
    if system_prompt is None:
        # PRTS mode is always enabled now as it's the only mode
        pass
    
    agent = RagAgent(
        llm=llm,
        retriever=retriever,
        system_prompt=system_prompt,
        compressor=compressor,
        enable_compression=args.enable_compression,
        session_id=args.session_id,
        memory_manager=memory_manager,
        memory_k=args.memory_k,
        use_dual_output=use_dual_output,
        use_anthropic_sdk=use_anthropic
    )
    agent.output_formatter.show_thinking = show_thinking
    agent.run()


if __name__ == "__main__":
    main()
