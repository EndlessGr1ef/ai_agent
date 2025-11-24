"""
环境变量配置文件，解决HuggingFace tokenizers并行处理警告
"""

import os

def configure_tokenizers():
    """配置HuggingFace tokenizers环境变量"""
    
    # 方案1：禁用tokenizers并行处理（推荐用于多进程应用）
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    
    # 方案2：如果你的应用不使用多进程，可以启用并行处理
    # os.environ["TOKENIZERS_PARALLELISM"] = "true"
    
    print("✅ HuggingFace tokenizers 并行处理配置完成")

def configure_transformers():
    """配置其他transformers相关环境变量"""
    
    # 禁用transformers的进度条（可选）
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
    
    # 设置缓存目录（可选）
    if not os.environ.get("TRANSFORMERS_CACHE"):
        os.environ["TRANSFORMERS_CACHE"] = os.path.expanduser("~/.cache/huggingface")
    
    # 禁用telemetry（可选）
    os.environ["TRANSFORMERS_OFFLINE"] = "0"

def configure_environment():
    """配置所有相关环境变量"""
    configure_tokenizers()
    configure_transformers()
    
    print("🔧 环境配置完成")

# 在导入其他模块之前自动配置
if __name__ == "__main__":
    configure_environment()
else:
    # 模块被导入时自动配置
    configure_tokenizers()