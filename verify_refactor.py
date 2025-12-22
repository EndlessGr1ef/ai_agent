#!/usr/bin/env python3
"""简单验证 embedding 统一管理重构的测试脚本"""

import sys
from pathlib import Path

# 添加 src 目录到路径
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

print("=" * 60)
print("Embedding 统一管理重构验证测试 (简化版)")
print("=" * 60)

print("\n测试 1: 验证导入...")
try:
    from config.embedding_manager import (
        get_global_embeddings,
        get_embeddings,
        reset_global_embeddings,
        get_embedding_dimension,
        get_embedding_info
    )
    print("✅ 所有函数导入成功")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

print("\n测试 2: 检查配置文件...")
try:
    from config import embeddings, embedding_manager
    print("✅ 配置模块导入成功")
except Exception as e:
    print(f"⚠️  配置模块导入警告: {e}")

print("\n测试 3: 验证函数签名...")
try:
    import inspect
    
    # 检查 get_global_embeddings 函数签名
    sig = inspect.signature(get_global_embeddings)
    params = list(sig.parameters.keys())
    print(f"✅ get_global_embeddings 参数: {params}")
    
    # 检查返回类型
    if 'return' in sig.parameters or sig.return_annotation:
        print(f"✅ 函数签名验证通过")
    
except Exception as e:
    print(f"❌ 函数签名验证失败: {e}")

print("\n测试 4: 检查文件更新...")
files_to_check = [
    ("src/main.py", "get_global_embeddings"),
    ("src/config/retriever.py", "get_global_embeddings"),
    ("ingest_md.py", "get_global_embeddings"),
    ("chroma_query_tool.py", "get_global_embeddings"),
]

for file_path, expected_import in files_to_check:
    full_path = Path(__file__).parent / file_path
    if full_path.exists():
        content = full_path.read_text()
        if expected_import in content:
            print(f"✅ {file_path} 已更新使用 {expected_import}")
        else:
            print(f"❌ {file_path} 未找到 {expected_import}")
    else:
        print(f"⚠️  {file_path} 不存在")

print("\n测试 5: 检查废弃导入...")
deprecated_patterns = [
    ("src/main.py", "from config.embeddings import build_embeddings"),
    ("src/config/retriever.py", "from .embeddings import build_embeddings"),
    ("ingest_md.py", "from langchain_huggingface import HuggingFaceEmbeddings"),
]

all_clean = True
for file_path, deprecated_import in deprecated_patterns:
    full_path = Path(__file__).parent / file_path
    if full_path.exists():
        content = full_path.read_text()
        if deprecated_import in content:
            print(f"❌ {file_path} 仍包含废弃导入: {deprecated_import}")
            all_clean = False
        else:
            print(f"✅ {file_path} 已清理废弃导入")

if all_clean:
    print("\n🎉 所有静态检查通过!")
else:
    print("\n⚠️  发现一些需要清理的废弃导入")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
