"""Enhanced embedding model configuration with optimized settings."""

import os
from typing import Optional, Dict, Any

from langchain_huggingface import HuggingFaceEmbeddings


def build_embeddings(
    model_name: Optional[str] = None, 
    cache_folder: Optional[str] = None,
    **kwargs
) -> HuggingFaceEmbeddings:
    """Create an optimized local embedding model.
    
    Args:
        model_name: Embedding model name. If None, uses environment variable or optimized default
        cache_folder: Directory to cache model files
        **kwargs: Additional arguments for HuggingFaceEmbeddings
    
    Returns:
        Configured HuggingFaceEmbeddings instance
    """
    if not model_name:
        # Use optimized default model for better performance
        model_name = os.getenv(
            "EMBED_MODEL_NAME", 
            "BAAI/bge-large-zh-v1.5"  # Better for Chinese + English technical content
        )
    
    # Set up model configuration with optimizations
    model_kwargs = {
        'device': 'cpu',  # Use CPU for compatibility
        'trust_remote_code': True  # Allow custom model code
    }
    
    # Encoding configuration for better performance
    encode_kwargs = {
        'normalize_embeddings': True,  # Normalize for better similarity scores
        'batch_size': 32,             # Batch processing for efficiency
    }
    
    # Override with user-provided kwargs
    model_kwargs.update(kwargs.get('model_kwargs', {}))
    encode_kwargs.update(kwargs.get('encode_kwargs', {}))
    
    # Set cache folder if provided
    if cache_folder:
        model_kwargs['cache_folder'] = cache_folder
    
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs=model_kwargs,
        encode_kwargs=encode_kwargs
    )


def build_optimized_embeddings(config_profile: str = "balanced") -> HuggingFaceEmbeddings:
    """Build embeddings with predefined optimization profiles.
    
    Args:
        config_profile: One of 'performance', 'quality', 'balanced'
    
    Returns:
        Configured embeddings instance
    """
    profiles = {
        "performance": {
            "model_name": "sentence-transformers/all-MiniLM-L6-v2",  # Fast, smaller model
            "encode_kwargs": {"batch_size": 64, "normalize_embeddings": True}
        },
        "quality": {
            "model_name": "BAAI/bge-large-zh-v1.5",  # High quality multilingual
            "encode_kwargs": {"batch_size": 16, "normalize_embeddings": True}
        },
        "balanced": {
            "model_name": "BAAI/bge-base-zh-v1.5",  # Good balance
            "encode_kwargs": {"batch_size": 32, "normalize_embeddings": True}
        }
    }
    
    profile_config = profiles.get(config_profile, profiles["balanced"])
    return build_embeddings(**profile_config)


# Model recommendations by use case
EMBEDDING_MODELS = {
    "chinese_technical": "BAAI/bge-large-zh-v1.5",      # Best for Chinese + English technical
    "english_technical": "BAAI/bge-large-en-v1.5",       # Best for English technical
    "multilingual": "intfloat/e5-large-v2",              # Good multilingual support  
    "fast_general": "sentence-transformers/all-MiniLM-L6-v2",  # Fast and efficient
    "code_search": "microsoft/codebert-base",             # Specialized for code
    "domain_specific": "sentence-transformers/all-mpnet-base-v2"  # Good general purpose
}


def get_recommended_model(use_case: str = "chinese_technical") -> str:
    """Get recommended embedding model for specific use case."""
    return EMBEDDING_MODELS.get(use_case, EMBEDDING_MODELS["chinese_technical"])
