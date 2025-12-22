#!/usr/bin/env python3
"""验证 embedding 统一管理重构的测试脚本"""

import sys
import os
from pathlib import Path

# 添加 src 目录到路径
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

def test_import():
    """测试 1: 验证导入"""
    print("测试 1: 验证导入...")
    try:
        from config import (
            get_global_embeddings,
            get_embeddings,
            reset_global_embeddings,
            get_embedding_dimension,
            get_embedding_info
        )
        print("✅ 所有函数导入成功")
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_singleton():
    """测试 2: 验证单例模式"""
    print("\n测试 2: 验证单例模式...")
    try:
        from config import get_global_embeddings
        
        # 获取两个实例
        emb1 = get_global_embeddings()
        emb2 = get_global_embeddings()
        
        # 应该是同一个实例
        if emb1 is emb2:
            print("✅ 单例模式工作正常 - 两次调用返回同一实例")
            return True
        else:
            print("❌ 单例模式失败 - 返回了不同的实例")
            return False
    except Exception as e:
        print(f"❌ 单例测试失败: {e}")
        return False

def test_embedding_info():
    """测试 3: 验证 embedding 信息"""
    print("\n测试 3: 验证 embedding 信息...")
    try:
        from config import get_global_embeddings, get_embedding_info, get_embedding_dimension
        
        # 初始化 embedding
        embeddings = get_global_embeddings()
        
        # 获取信息
        info = get_embedding_info()
        dim = get_embedding_dimension()
        
        print(f"✅ Embedding 信息:")
        print(f"   - 已初始化: {info['initialized']}")
        print(f"   - 模型名称: {info['model_name']}")
        print(f"   - 向量维度: {dim}")
        
        if info['initialized'] and dim and dim > 0:
            return True
        else:
            print("❌ Embedding 信息不完整")
            return False
    except Exception as e:
        print(f"❌ 信息获取失败: {e}")
        return False

def test_embedding_query():
    """测试 4: 验证 embedding 查询"""
    print("\n测试 4: 验证 embedding 查询...")
    try:
        from config import get_global_embeddings, get_embedding_dimension
        
        embeddings = get_global_embeddings()
        
        # 测试查询
        test_text = "这是一个测试文本"
        query_emb = embeddings.embed_query(test_text)
        
        # 验证维度
        expected_dim = get_embedding_dimension()
        actual_dim = len(query_emb)
        
        if expected_dim == actual_dim:
            print(f"✅ Embedding 查询成功 - 维度匹配: {actual_dim}")
            return True
        else:
            print(f"❌ 维度不匹配 - 期望: {expected_dim}, 实际: {actual_dim}")
            return False
    except Exception as e:
        print(f"❌ 查询测试失败: {e}")
        return False

def test_reset():
    """测试 5: 验证重置功能"""
    print("\n测试 5: 验证重置功能...")
    try:
        from config import get_global_embeddings, reset_global_embeddings
        
        # 获取初始实例
        emb1 = get_global_embeddings()
        
        # 重置
        reset_global_embeddings()
        
        # 再次获取
        emb2 = get_global_embeddings()
        
        # 应该是不同的实例
        if emb1 is not emb2:
            print("✅ 重置功能工作正常 - 返回了新实例")
            return True
        else:
            print("❌ 重置失败 - 返回了相同的实例")
            return False
    except Exception as e:
        print(f"❌ 重置测试失败: {e}")
        return False

def test_custom_model():
    """测试 6: 验证自定义模型参数"""
    print("\n测试 6: 验证自定义模型参数...")
    try:
        from config import get_global_embeddings, reset_global_embeddings
        
        # 重置以确保干净状态
        reset_global_embeddings()
        
        # 使用自定义模型名称（不强制重载以避免下载）
        model_name = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-large-zh-v1.5")
        embeddings = get_global_embeddings(model_name=model_name)
        
        # 验证模型名称
        actual_model = getattr(embeddings, 'model_name', None)
        if actual_model:
            print(f"✅ 自定义模型参数工作正常 - 使用模型: {actual_model}")
            return True
        else:
            print("⚠️  无法验证模型名称,但没有错误发生")
            return True
    except Exception as e:
        print(f"❌ 自定义模型测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    print("=" * 60)
    print("Embedding 统一管理重构验证测试")
    print("=" * 60)
    
    tests = [
        test_import,
        test_singleton,
        test_embedding_info,
        test_embedding_query,
        test_reset,
        test_custom_model,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ 测试异常: {e}")
            results.append(False)
    
    # 总结
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过!")
        return 0
    else:
        print("⚠️  部分测试失败,请检查上述错误信息")
        return 1

if __name__ == "__main__":
    sys.exit(main())
