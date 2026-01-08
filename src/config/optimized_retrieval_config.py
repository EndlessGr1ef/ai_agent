"""Optimized retrieval configuration for improved RAG performance."""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class OptimizedRetrievalConfig:
    """Optimized configuration for RAG retrieval system."""
    
    # ========== Embedding Model Settings ==========
    # Use more powerful embedding model for better semantic understanding
    embedding_model: str = field(default_factory=lambda: os.getenv(
        "EMBED_MODEL_NAME", 
        "BAAI/bge-large-zh-v1.5"  # Better for Chinese + English technical content
    ))
    
    # Alternative models based on use case:
    # - "BAAI/bge-large-en-v1.5" - English technical content
    # - "BAAI/bge-large-zh-v1.5" - Chinese + English mixed
    # - "sentence-transformers/all-mpnet-base-v2" - General purpose
    # - "intfloat/e5-large-v2" - Multilingual
    
    # ========== Chunking Strategy ==========
    adaptive_chunking: bool = True
    
    # Document-type specific chunking
    chunk_configs: Dict[str, Dict[str, int]] = field(default_factory=lambda: {
        "code": {
            "chunk_size": 1500,    # Larger for code to preserve function context
            "chunk_overlap": 300   # More overlap to keep related code together
        },
        "documentation": {
            "chunk_size": 1200,    # Medium for structured docs
            "chunk_overlap": 250
        },
        "tutorial": {
            "chunk_size": 800,     # Smaller for step-by-step content
            "chunk_overlap": 150
        },
        "api": {
            "chunk_size": 1000,    # Standard for API docs
            "chunk_overlap": 200
        },
        "distilled": {
            "chunk_size": 2500,    # Larger for distilled content to keep as single semantic unit
            "chunk_overlap": 200
        },
        "default": {
            "chunk_size": 1000,    # Fallback
            "chunk_overlap": 200
        }
    })
    
    # ========== Retrieval Parameters ==========
    # Multi-stage retrieval: retrieve more, then filter down
    initial_retrieval_k: int = 30      # Increased for better recall
    final_result_k: int = 15           # Increased for more comprehensive context
    
    # Similarity thresholds
    similarity_threshold: float = 0.50  # Lowered to be much more inclusive initially
    rerank_threshold: float = 0.60      # Adjusted threshold after reranking
    
    # ========== Query Enhancement ==========
    enable_query_expansion: bool = True
    enable_query_rewriting: bool = True
    enable_multi_query: bool = True     # Generate multiple query variations
    
    query_expansion_terms: int = 3      # Max synonyms/related terms to add
    max_query_variants: int = 3         # Max alternative query formulations
    
    # ========== Reranking Configuration ==========
    enable_reranking: bool = True
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    
    # Alternative rerankers:
    # - "cross-encoder/ms-marco-MiniLM-L-12-v2" - Better but slower
    # - "BAAI/bge-reranker-base" - Good for technical content
    
    # ========== Context Building ==========
    max_context_tokens: int = 12000     # Increased for more documents
    enable_context_compression: bool = True
    enable_source_grouping: bool = True  # Group content by source
    enable_relevance_scoring: bool = True
    
    # Deduplication settings
    enable_deduplication: bool = True
    content_similarity_threshold: float = 0.8
    
    # ========== Memory Integration ==========
    memory_weight: float = 0.3          # Weight for memory vs document context
    max_memory_context: int = 2000      # Max tokens from memory
    
    # ========== Performance Optimization ==========
    cache_embeddings: bool = True       # Cache query embeddings
    batch_size: int = 32               # Batch size for embedding generation
    
    # Parallel processing
    enable_parallel_queries: bool = True
    max_concurrent_queries: int = 3
    
    # ========== Quality Monitoring ==========
    enable_metrics: bool = True         # Track retrieval performance
    log_retrieval_details: bool = False # Detailed logging (for debugging)
    
    # Success metrics thresholds
    min_retrieval_score: float = 0.3   # Lowered to allow more results
    target_response_time: float = 3.0  # Increased for more complex retrieval
    
    
# Predefined configurations for different scenarios
PERFORMANCE_CONFIG = OptimizedRetrievalConfig(
    # Fast retrieval with basic quality
    embedding_model=os.getenv("EMBED_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"),
    initial_retrieval_k=8,
    final_result_k=4,
    enable_reranking=False,
    enable_query_expansion=False,
    max_context_tokens=6000
)

QUALITY_CONFIG = OptimizedRetrievalConfig(
    # High quality with advanced features
    embedding_model=os.getenv("EMBED_MODEL_NAME", "BAAI/bge-large-zh-v1.5"),
    initial_retrieval_k=30,
    final_result_k=15,
    enable_reranking=True,
    enable_query_expansion=True,
    enable_multi_query=True,
    max_context_tokens=15000,
    reranker_model="cross-encoder/ms-marco-MiniLM-L-12-v2"
)

BALANCED_CONFIG = OptimizedRetrievalConfig(
    # Balanced performance and quality (default)
    embedding_model=os.getenv("EMBED_MODEL_NAME", "BAAI/bge-large-zh-v1.5"),
    initial_retrieval_k=30,
    final_result_k=15,
    enable_reranking=True,
    enable_query_expansion=True,
    max_context_tokens=12000
)


def get_config_by_name(config_name: str = "balanced") -> OptimizedRetrievalConfig:
    """Get predefined configuration by name."""
    configs = {
        "performance": PERFORMANCE_CONFIG,
        "quality": QUALITY_CONFIG,
        "balanced": BALANCED_CONFIG,
        "default": BALANCED_CONFIG
    }
    
    return configs.get(config_name.lower(), BALANCED_CONFIG)


def get_chunk_config(document_type: str, config: OptimizedRetrievalConfig) -> Dict[str, int]:
    """Get appropriate chunking configuration for document type."""
    if not config.adaptive_chunking:
        return config.chunk_configs["default"]
    
    # Detect document type from metadata or content
    doc_type_lower = document_type.lower()
    
    # Map various document type indicators
    type_mappings = {
        "code": ["code", "python", "javascript", "java", "cpp", "programming"],
        "documentation": ["doc", "documentation", "manual", "guide", "readme"],
        "tutorial": ["tutorial", "howto", "example", "demo", "walkthrough"],
        "api": ["api", "reference", "endpoint", "swagger", "openapi"],
        "distilled": ["distilled", "summary", "refined"]
    }
    
    for chunk_type, indicators in type_mappings.items():
        if any(indicator in doc_type_lower for indicator in indicators):
            return config.chunk_configs[chunk_type]
    
    return config.chunk_configs["default"]


# Environment-based configuration
def load_config_from_env() -> OptimizedRetrievalConfig:
    """Load configuration from environment variables."""
    config_name = os.getenv("RAG_CONFIG_PROFILE", "balanced")
    base_config = get_config_by_name(config_name)
    
    # Override with environment variables if present
    if os.getenv("EMBED_MODEL_NAME"):
        base_config.embedding_model = os.getenv("EMBED_MODEL_NAME")
    
    if os.getenv("RAG_INITIAL_K"):
        base_config.initial_retrieval_k = int(os.getenv("RAG_INITIAL_K"))
    
    if os.getenv("RAG_FINAL_K"):
        base_config.final_result_k = int(os.getenv("RAG_FINAL_K"))
    
    if os.getenv("RAG_ENABLE_RERANKING"):
        base_config.enable_reranking = os.getenv("RAG_ENABLE_RERANKING").lower() == "true"
    
    if os.getenv("RAG_MAX_CONTEXT_TOKENS"):
        base_config.max_context_tokens = int(os.getenv("RAG_MAX_CONTEXT_TOKENS"))
    
    return base_config