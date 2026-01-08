"""Enhanced retriever configuration utilities with optimization support."""

from typing import Optional, Dict, Any, Union, TYPE_CHECKING
from .embedding_manager import get_global_embeddings
from .llm_config import create_chroma_client
from langchain_chroma import Chroma

# Always import optimized retrieval config (doesn't depend on enhanced module)
from .optimized_retrieval_config import (
    OptimizedRetrievalConfig,
    get_config_by_name,
    load_config_from_env,
)

# Import enhanced retrieval if available (optional dependency)
try:
    from rag.enhanced_retrieval import EnhancedRAGRetriever, RetrievalConfig
    ENHANCED_AVAILABLE = True
except Exception as e:
    print(f"DEBUG: Enhanced retrieval import failed: {e}")
    ENHANCED_AVAILABLE = False


def build_retriever(
    collection_name: str,
    host: str,
    port: int,
    embed_model_name: Optional[str] = None,
    top_k: int = 4,
    category_filter: Optional[str] = None,
    subcategory_filter: Optional[str] = None,
    topic_filter: Optional[str] = None,
    language_filter: Optional[str] = None,
    # Enhanced parameters
    use_enhanced: bool = True,
    config_profile: str = "balanced",
    custom_config: Optional[OptimizedRetrievalConfig] = None,
    # Distilled content prioritization
    prefer_distilled: bool = True,
    distilled_ratio: float = 0.6
):
    """
    Create an enhanced retriever backed by Chroma collection with optional optimization.

    Args:
        collection_name: Chroma collection name
        host: Chroma server host  
        port: Chroma server port
        embed_model_name: Embedding model name (overrides config profile)
        top_k: Number of chunks to retrieve (for basic retriever)
        category_filter: Filter by category (e.g., "AI/RAG", "Backend")
        subcategory_filter: Filter by subcategory (e.g., "RAG", "Go")
        topic_filter: Filter by topic
        language_filter: Filter by programming language
        use_enhanced: Whether to use enhanced retrieval system
        config_profile: Configuration profile ('performance', 'quality', 'balanced')
        custom_config: Custom retrieval configuration (overrides profile)
        prefer_distilled: Prioritize distilled (refined) content over raw content
        distilled_ratio: Target ratio of distilled content (default: 0.6 = 60% distilled)
    
    Returns:
        Enhanced retriever if available, otherwise basic retriever
    """
    
    # Build embeddings with optimized settings - always use global instance
    embeddings = get_global_embeddings(model_name=embed_model_name)
    
    # Create Chroma client and vector store
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

    # Configure search parameters based on enhancement settings
    if use_enhanced and ENHANCED_AVAILABLE:
        # Use enhanced configuration
        opt_config = custom_config or get_config_by_name(config_profile)
        search_kwargs = {"k": opt_config.initial_retrieval_k}
        if filter_dict:
            search_kwargs["filter"] = filter_dict
            
        base_retriever = vs.as_retriever(search_kwargs=search_kwargs)
        
        # Convert to RetrievalConfig
        retrieval_config = RetrievalConfig(
            initial_k=opt_config.initial_retrieval_k,
            final_k=opt_config.final_result_k,
            similarity_threshold=opt_config.similarity_threshold,
            use_reranking=opt_config.enable_reranking,
            reranker_model=opt_config.reranker_model,
            enable_query_expansion=opt_config.enable_query_expansion,
            enable_query_rewrite=opt_config.enable_query_rewriting,
            max_context_length=opt_config.max_context_tokens,
            enable_deduplication=opt_config.enable_deduplication,
            similarity_dedup_threshold=opt_config.content_similarity_threshold,
            # Distilled content prioritization
            prefer_distilled=prefer_distilled,
            distilled_ratio=distilled_ratio
        )
        
        print(f"✓ Enhanced retriever initialized with '{config_profile}' profile")
        if prefer_distilled:
            print(f"  ➜ Distilled content priority enabled (ratio: {distilled_ratio:.0%})")
        return EnhancedRAGRetriever(base_retriever, retrieval_config)
    else:
        # Use basic configuration
        search_kwargs = {"k": top_k}
        if filter_dict:
            search_kwargs["filter"] = filter_dict
            
        basic_retriever = vs.as_retriever(search_kwargs=search_kwargs)
        
        if use_enhanced:
            print("⚠️  Enhanced retrieval requested but not available, using basic retriever")
        
        return basic_retriever
