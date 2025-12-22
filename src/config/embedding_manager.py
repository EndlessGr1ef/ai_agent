"""全局 Embedding 模型管理器 - 确保项目中使用统一的 embedding 模型。

使用单例模式，确保整个应用程序只有一个 embedding 实例，避免：
1. 维度不匹配问题
2. 重复加载模型浪费内存
3. 配置不一致导致的错误

使用方法:
    from config.embedding_manager import get_global_embeddings
    
    # 获取全局 embedding 实例
    embeddings = get_global_embeddings()
    
    # 或强制重新初始化（通常不需要）
    embeddings = get_global_embeddings(force_reload=True)
"""

import os
import logging
from typing import Optional
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from .embeddings import build_embeddings

logger = logging.getLogger(__name__)

# 全局单例实例
_global_embeddings_instance: Optional[HuggingFaceEmbeddings] = None
_global_embeddings_config: Optional[dict] = None


def get_global_embeddings(
    model_name: Optional[str] = None,
    cache_folder: Optional[str] = None,
    force_reload: bool = False,
    **kwargs
) -> HuggingFaceEmbeddings:
    """获取全局 embedding 实例（单例模式）。
    
    首次调用时会初始化 embedding 模型，后续调用返回同一实例。
    这确保了整个应用程序使用相同的 embedding 配置。
    
    Args:
        model_name: 模型名称（仅在首次初始化或 force_reload=True 时使用）
        cache_folder: 缓存目录（仅在首次初始化或 force_reload=True 时使用）
        force_reload: 是否强制重新加载模型
        **kwargs: 其他传递给 build_embeddings 的参数
    
    Returns:
        全局 HuggingFaceEmbeddings 实例
    
    Examples:
        >>> # 获取全局实例（首次调用会初始化）
        >>> embeddings = get_global_embeddings()
        >>> 
        >>> # 后续调用返回同一实例
        >>> same_embeddings = get_global_embeddings()
        >>> assert embeddings is same_embeddings
        >>> 
        >>> # 强制重新加载（例如切换模型时）
        >>> new_embeddings = get_global_embeddings(
        ...     model_name="sentence-transformers/all-MiniLM-L6-v2",
        ...     force_reload=True
        ... )
    """
    global _global_embeddings_instance, _global_embeddings_config
    
    # 构建当前配置
    current_config = {
        'model_name': model_name or os.getenv('EMBED_MODEL_NAME', 'BAAI/bge-large-zh-v1.5'),
        'cache_folder': cache_folder,
        **kwargs
    }
    
    # 如果实例不存在，或配置变化，或强制重新加载，则重新初始化
    if (_global_embeddings_instance is None or 
        _global_embeddings_config != current_config or 
        force_reload):
        
        if _global_embeddings_instance is not None:
            logger.info("🔄 重新初始化全局 embedding 模型")
        else:
            logger.info("🚀 首次初始化全局 embedding 模型")
        
        # 使用统一的 build_embeddings 创建实例
        _global_embeddings_instance = build_embeddings(
            model_name=current_config['model_name'],
            cache_folder=current_config['cache_folder'],
            **{k: v for k, v in current_config.items() 
               if k not in ['model_name', 'cache_folder']}
        )
        _global_embeddings_config = current_config
        
        # 记录模型信息
        model_info = getattr(_global_embeddings_instance, 'model_name', 'unknown')
        logger.info(f"✓ 全局 embedding 模型已加载: {model_info}")
        
        # 获取并记录向量维度（通过编码一个测试文本）
        try:
            test_embedding = _global_embeddings_instance.embed_query("test")
            dimension = len(test_embedding)
            logger.info(f"✓ Embedding 向量维度: {dimension}")
        except Exception as e:
            logger.warning(f"⚠️  无法获取向量维度: {e}")
    
    return _global_embeddings_instance


def reset_global_embeddings():
    """重置全局 embedding 实例。
    
    主要用于测试或需要切换完全不同配置的场景。
    在正常使用中很少需要调用此函数。
    """
    global _global_embeddings_instance, _global_embeddings_config
    
    logger.info("🔄 重置全局 embedding 实例")
    _global_embeddings_instance = None
    _global_embeddings_config = None


def get_embedding_dimension() -> Optional[int]:
    """获取当前全局 embedding 模型的向量维度。
    
    Returns:
        向量维度，如果模型未初始化则返回 None
    """
    if _global_embeddings_instance is None:
        return None
    
    try:
        test_embedding = _global_embeddings_instance.embed_query("test")
        return len(test_embedding)
    except Exception as e:
        logger.error(f"获取向量维度失败: {e}")
        return None


def get_embedding_info() -> dict:
    """获取当前全局 embedding 模型的详细信息。
    
    Returns:
        包含模型信息的字典
    """
    if _global_embeddings_instance is None:
        return {
            'initialized': False,
            'model_name': None,
            'dimension': None,
            'config': None
        }
    
    return {
        'initialized': True,
        'model_name': getattr(_global_embeddings_instance, 'model_name', 'unknown'),
        'dimension': get_embedding_dimension(),
        'config': _global_embeddings_config
    }


# 便捷别名
get_embeddings = get_global_embeddings
