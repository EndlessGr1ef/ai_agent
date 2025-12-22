"""Enhanced embedding model configuration with optimized settings."""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import logging

from langchain_huggingface import HuggingFaceEmbeddings

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


def get_local_model_cache_dir() -> Path:
    """获取本地模型缓存目录。
    
    优先级：
    1. EMBED_CACHE_DIR 环境变量
    2. ~/.cache/huggingface/hub (HuggingFace 默认)
    
    Returns:
        本地模型缓存目录路径
    """
    cache_dir = os.getenv("EMBED_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser()
    
    # HuggingFace 默认缓存目录
    return Path.home() / ".cache" / "huggingface" / "hub"


def check_model_cached(model_name: str, cache_dir: Optional[Path] = None) -> Optional[str]:
    """检查模型是否已在本地缓存。
    
    Args:
        model_name: 模型名称或路径
        cache_dir: 缓存目录（可选）
    
    Returns:
        如果找到本地模型返回模型名称（HuggingFace 会自动使用缓存），否则返回 None
    """
    # 如果已经是本地路径，直接检查
    model_path = Path(model_name)
    if model_path.exists() and model_path.is_dir():
        logger.info(f"✓ 使用本地模型: {model_path}")
        return str(model_path)
    
    # 检查缓存目录
    if not cache_dir:
        cache_dir = get_local_model_cache_dir()
    
    if not cache_dir.exists():
        return None
    
    # HuggingFace Hub 缓存格式: models--组织名--模型名
    # 例如: models--BAAI--bge-large-zh-v1.5
    safe_model_name = model_name.replace("/", "--")
    cached_model_dir = cache_dir / f"models--{safe_model_name}"
    
    if cached_model_dir.exists():
        # 在 snapshots 中查找最新版本
        snapshots_dir = cached_model_dir / "snapshots"
        if snapshots_dir.exists():
            snapshots = list(snapshots_dir.iterdir())
            if snapshots:
                # 找到缓存，但返回原始模型名让 HuggingFace 自动使用缓存
                logger.info(f"✓ 找到本地缓存模型: {model_name}")
                return model_name
    
    return None


def resolve_model_path(model_name: str, cache_folder: Optional[str] = None) -> str:
    """解析模型路径，优先使用本地缓存。
    
    Args:
        model_name: 模型名称或路径
        cache_folder: 自定义缓存目录
    
    Returns:
        解析后的模型路径（本地路径或 HuggingFace Hub 名称）
    """
    # 检查是否设置了本地模型路径环境变量
    local_model_path = os.getenv("EMBED_LOCAL_MODEL_PATH")
    if local_model_path:
        local_path = Path(local_model_path).expanduser()
        if local_path.exists():
            logger.info(f"✓ 使用环境变量指定的本地模型: {local_path}")
            return str(local_path)
        else:
            logger.warning(f"⚠️  环境变量 EMBED_LOCAL_MODEL_PATH 指定的路径不存在: {local_path}")
    
    # 检查本地缓存（返回模型名让 HuggingFace 自动使用缓存）
    cache_dir = Path(cache_folder) if cache_folder else None
    cached_model_name = check_model_cached(model_name, cache_dir)
    if cached_model_name:
        return cached_model_name
    
    # 未找到本地缓存，返回原始模型名（将从 HuggingFace Hub 下载）
    logger.info(f"ℹ️  本地未找到模型 {model_name}，将从 HuggingFace Hub 下载")
    return model_name


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
    
    # 如果未指定缓存目录，使用默认缓存目录
    if not cache_folder:
        cache_folder = str(get_local_model_cache_dir())
    
    # 解析模型路径（优先使用本地缓存）
    resolved_model_path = resolve_model_path(model_name, cache_folder)
    
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
    
    # 设置 HuggingFace 镜像（如果需要下载模型）
    if not Path(resolved_model_path).exists():
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    
    # cache_folder 需要作为顶层参数传递，而不是放在 model_kwargs 中
    embedding_params = {
        'model_name': resolved_model_path,
        'model_kwargs': model_kwargs,
        'encode_kwargs': encode_kwargs
    }
    
    if cache_folder:
        embedding_params['cache_folder'] = cache_folder
    
    return HuggingFaceEmbeddings(**embedding_params)


def build_optimized_embeddings(config_profile: str = "balanced") -> HuggingFaceEmbeddings:
    """Build embeddings with predefined optimization profiles.
    
    Args:
        config_profile: One of 'performance', 'quality', 'balanced'
    
    Returns:
        Configured embeddings instance
    """
    # 从环境变量获取模型，如果没有则使用默认值
    env_model_name = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-large-zh-v1.5")
    
    profiles = {
        "performance": {
            "model_name": env_model_name if env_model_name else "sentence-transformers/all-MiniLM-L6-v2",  # Fast, smaller model
            "encode_kwargs": {"batch_size": 64, "normalize_embeddings": True}
        },
        "quality": {
            "model_name": env_model_name,  # High quality multilingual
            "encode_kwargs": {"batch_size": 16, "normalize_embeddings": True}
        },
        "balanced": {
            "model_name": env_model_name,  # Good balance
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
    """Get recommended embedding model for specific use case.
    
    If EMBED_MODEL_NAME environment variable is set, it takes precedence.
    Otherwise, returns model based on the specified use case.
    """
    # 环境变量优先
    env_model = os.getenv("EMBED_MODEL_NAME")
    if env_model:
        return env_model
    
    # 否则返回基于用例的推荐模型
    return EMBEDDING_MODELS.get(use_case, EMBEDDING_MODELS["chinese_technical"])
