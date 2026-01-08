#!/usr/bin/env python3
"""
Clear all ChromaDB collections
清空 ChromaDB 所有数据
"""

import chromadb
from chromadb.config import Settings
import sys


def clear_all_collections(host="localhost", port=9000, auto_confirm=False):
    """
    Clear all collections in ChromaDB
    
    Args:
        host: ChromaDB host
        port: ChromaDB port
        auto_confirm: If True, skip confirmation prompt
    """
    try:
        # Connect to ChromaDB
        client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=Settings(anonymized_telemetry=False)
        )
        
        collections = client.list_collections()
        
        if not collections:
            print("ℹ️  ChromaDB 中没有任何 collections")
            return
        
        print(f"✅ 成功连接到 ChromaDB ({host}:{port})")
        print(f"📋 发现 {len(collections)} 个 collections:\n")
        
        # List all collections with document count
        total_docs = 0
        for i, col_obj in enumerate(collections, 1):
            try:
                col_name = col_obj.name if hasattr(col_obj, 'name') else str(col_obj)
                col = client.get_collection(col_name)
                count = col.count()
                total_docs += count
                print(f"  {i}. {col_name} ({count} 文档)")
            except Exception as e:
                print(f"  {i}. {col_obj} (获取失败: {e})")
        
        print(f"\n📊 总计: {len(collections)} collections, {total_docs} 文档")
        
        # Confirm deletion
        if not auto_confirm:
            print("\n" + "="*60)
            print("⚠️  警告: 此操作将删除所有 collections 及其数据")
            print("⚠️  此操作不可撤销!")
            print("="*60)
            
            confirm = input("\n确定要清空所有数据吗？(输入 'yes' 确认): ").strip()
            
            if confirm.lower() != 'yes':
                print("❌ 已取消操作")
                return
        
        # Delete all collections
        print("\n🗑️  开始删除...")
        deleted_count = 0
        
        for col_obj in collections:
            try:
                col_name = col_obj.name if hasattr(col_obj, 'name') else str(col_obj)
                client.delete_collection(col_name)
                deleted_count += 1
                print(f"  ✓ 已删除: {col_name}")
            except Exception as e:
                print(f"  ✗ 删除失败 {col_name}: {e}")
        
        # Verify
        remaining = client.list_collections()
        
        print(f"\n{'='*60}")
        print(f"✅ 完成! 已删除 {deleted_count}/{len(collections)} 个 collections")
        print(f"📋 剩余 collections: {len(remaining)} 个")
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        print("请确保 ChromaDB 服务正在运行")
        sys.exit(1)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Clear all ChromaDB collections',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--host',
        type=str,
        default='localhost',
        help='ChromaDB host (default: localhost)'
    )
    
    parser.add_argument(
        '--port',
        type=int,
        default=9000,
        help='ChromaDB port (default: 9000)'
    )
    
    parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("🧹 ChromaDB 清空工具")
    print("="*60 + "\n")
    
    clear_all_collections(
        host=args.host,
        port=args.port,
        auto_confirm=args.yes
    )


if __name__ == "__main__":
    main()
