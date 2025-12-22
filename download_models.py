#!/usr/bin/env python3
"""
模型下载工具 - 预下载和缓存 embedding 模型

使用方法:
    python download_models.py                    # 下载默认模型
    python download_models.py --model <模型名>    # 下载指定模型
    python download_models.py --list             # 列出推荐模型
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional

# 设置 HuggingFace 镜像以提升下载速度
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from sentence_transformers import SentenceTransformer


# 推荐的 embedding 模型列表
RECOMMENDED_MODELS = {
    "chinese_technical": {
        "name": "BAAI/bge-large-zh-v1.5",
        "description": "中英文技术内容（推荐，1024维）",
        "size": "~1.3GB",
        "dimension": 1024
    },
    "english_technical": {
        "name": "BAAI/bge-large-en-v1.5",
        "description": "英文技术内容（1024维）",
        "size": "~1.3GB",
        "dimension": 1024
    },
    "fast_general": {
        "name": "sentence-transformers/all-MiniLM-L6-v2",
        "description": "快速通用模型（384维）",
        "size": "~90MB",
        "dimension": 384
    },
    "multilingual": {
        "name": "intfloat/e5-large-v2",
        "description": "多语言支持（1024维）",
        "size": "~1.3GB",
        "dimension": 1024
    },
    "domain_general": {
        "name": "sentence-transformers/all-mpnet-base-v2",
        "description": "通用领域（768维）",
        "size": "~420MB",
        "dimension": 768
    }
}


def get_cache_dir() -> Path:
    """获取模型缓存目录"""
    cache_dir = os.getenv("EMBED_CACHE_DIR")
    if cache_dir:
        return Path(cache_dir).expanduser()
    return Path.home() / ".cache" / "huggingface" / "hub"


def list_recommended_models():
    """列出推荐的模型"""
    print("\n" + "="*70)
    print("📋 推荐的 Embedding 模型")
    print("="*70)
    
    for key, info in RECOMMENDED_MODELS.items():
        print(f"\n[{key}]")
        print(f"  模型名称: {info['name']}")
        print(f"  描述: {info['description']}")
        print(f"  大小: {info['size']}")
        print(f"  维度: {info['dimension']}")
    
    print("\n" + "="*70)
    print("\n💡 使用方式:")
    print("  python download_models.py --model BAAI/bge-large-zh-v1.5")
    print("  python download_models.py --model chinese_technical")
    print()


def check_model_exists(model_name: str) -> Optional[Path]:
    """检查模型是否已下载"""
    cache_dir = get_cache_dir()
    
    # 检查 HuggingFace Hub 缓存格式
    safe_model_name = model_name.replace("/", "--")
    cached_model_dir = cache_dir / f"models--{safe_model_name}"
    
    if cached_model_dir.exists():
        snapshots_dir = cached_model_dir / "snapshots"
        if snapshots_dir.exists():
            snapshots = list(snapshots_dir.iterdir())
            if snapshots:
                latest_snapshot = max(snapshots, key=lambda p: p.stat().st_mtime)
                return latest_snapshot
    
    return None


def download_model(model_name: str, force: bool = False) -> bool:
    """下载指定模型
    
    Args:
        model_name: 模型名称或别名
        force: 强制重新下载
    
    Returns:
        是否下载成功
    """
    # 如果是别名，转换为实际模型名
    if model_name in RECOMMENDED_MODELS:
        model_info = RECOMMENDED_MODELS[model_name]
        actual_model_name = model_info["name"]
        print(f"✓ 使用推荐模型: {model_info['description']}")
        print(f"  模型名称: {actual_model_name}")
        print(f"  预计大小: {model_info['size']}")
        print(f"  向量维度: {model_info['dimension']}")
    else:
        actual_model_name = model_name
    
    # 检查是否已存在
    if not force:
        existing_path = check_model_exists(actual_model_name)
        if existing_path:
            print(f"\n✅ 模型已存在于本地: {existing_path}")
            print(f"   如需重新下载，请使用 --force 参数")
            return True
    
    print(f"\n⬇️  开始下载模型: {actual_model_name}")
    print(f"   缓存目录: {get_cache_dir()}")
    print(f"   使用镜像: {os.getenv('HF_ENDPOINT', 'huggingface.co')}")
    print("\n⏳ 下载中，请稍候...\n")
    
    try:
        # 使用 SentenceTransformer 下载模型
        model = SentenceTransformer(actual_model_name, cache_folder=str(get_cache_dir()))
        
        print(f"\n✅ 模型下载成功!")
        print(f"   缓存位置: {get_cache_dir()}")
        
        # 验证模型
        test_embedding = model.encode("测试文本")
        print(f"   向量维度: {len(test_embedding)}")
        
        print(f"\n💡 使用方式:")
        print(f"   1. 设置环境变量: export EMBED_MODEL_NAME={actual_model_name}")
        print(f"   2. 或在 .env 文件中添加: EMBED_MODEL_NAME={actual_model_name}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        print("\n🔧 故障排除:")
        print("   1. 检查网络连接")
        print("   2. 尝试使用镜像: export HF_ENDPOINT=https://hf-mirror.com")
        print("   3. 检查磁盘空间")
        return False


def show_cache_info():
    """显示缓存信息"""
    cache_dir = get_cache_dir()
    print(f"\n📁 缓存目录: {cache_dir}")
    
    if not cache_dir.exists():
        print("   (目录不存在，尚未下载任何模型)")
        return
    
    # 统计已缓存的模型
    model_dirs = list(cache_dir.glob("models--*"))
    
    if not model_dirs:
        print("   (未找到已缓存的模型)")
        return
    
    print(f"\n✓ 已缓存 {len(model_dirs)} 个模型:\n")
    
    total_size = 0
    for model_dir in sorted(model_dirs):
        model_name = model_dir.name.replace("models--", "").replace("--", "/")
        
        # 计算大小
        size = sum(f.stat().st_size for f in model_dir.rglob('*') if f.is_file())
        total_size += size
        size_mb = size / (1024 * 1024)
        
        # 检查是否有 snapshots
        snapshots_dir = model_dir / "snapshots"
        snapshot_count = len(list(snapshots_dir.iterdir())) if snapshots_dir.exists() else 0
        
        print(f"  • {model_name}")
        print(f"    大小: {size_mb:.1f} MB")
        print(f"    版本数: {snapshot_count}")
    
    print(f"\n📊 总缓存大小: {total_size / (1024 * 1024):.1f} MB")


def main():
    parser = argparse.ArgumentParser(
        description="预下载和管理 Embedding 模型",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 列出推荐模型
  python download_models.py --list
  
  # 下载默认推荐模型（中英文技术内容）
  python download_models.py
  
  # 下载指定模型
  python download_models.py --model BAAI/bge-large-zh-v1.5
  
  # 使用别名下载
  python download_models.py --model chinese_technical
  
  # 强制重新下载
  python download_models.py --model chinese_technical --force
  
  # 查看缓存信息
  python download_models.py --cache-info
        """
    )
    
    parser.add_argument(
        "--model",
        type=str,
        help="要下载的模型名称或别名"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出推荐的模型"
    )
    
    parser.add_argument(
        "--cache-info",
        action="store_true",
        help="显示缓存信息"
    )
    
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制重新下载（即使已存在）"
    )
    
    parser.add_argument(
        "--mirror",
        type=str,
        default="https://hf-mirror.com",
        help="HuggingFace 镜像地址（默认: https://hf-mirror.com）"
    )
    
    args = parser.parse_args()
    
    # 设置镜像
    if args.mirror:
        os.environ["HF_ENDPOINT"] = args.mirror
    
    print("\n" + "="*70)
    print("🚀 Embedding 模型下载工具")
    print("="*70)
    
    # 显示缓存信息
    if args.cache_info:
        show_cache_info()
        return
    
    # 列出推荐模型
    if args.list:
        list_recommended_models()
        return
    
    # 下载模型
    model_to_download = args.model or "chinese_technical"
    success = download_model(model_to_download, args.force)
    
    if success:
        print("\n" + "="*70)
        print("✅ 完成!")
        print("="*70)
        sys.exit(0)
    else:
        print("\n" + "="*70)
        print("❌ 失败!")
        print("="*70)
        sys.exit(1)


if __name__ == "__main__":
    main()
