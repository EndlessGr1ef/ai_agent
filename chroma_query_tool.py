#!/usr/bin/env python3
"""
ChromaDB查询工具 - 本地交互式查询脚本

支持多种查询方式：
- 查看collections
- 统计信息
- 相似度搜索
- 条件过滤
- 文档查看
"""

import chromadb
from chromadb.config import Settings
from collections import Counter
from pathlib import Path
import os
import sys

class ChromaQueryTool:
    def __init__(self, host="localhost", port=9000):
        """初始化ChromaDB连接"""
        try:
            self.client = chromadb.HttpClient(
                host=host,
                port=port,
                settings=Settings(anonymized_telemetry=False)
            )
            self.collections = self.client.list_collections()
            print(f"✅ 成功连接到 ChromaDB ({host}:{port})")
            print(f"✅ 发现 {len(self.collections)} 个 collections\n")
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            print("请确保ChromaDB服务正在运行")
            sys.exit(1)

    def _get_collection_name(self, index):
        """从索引获取collection名称"""
        if 0 <= index < len(self.collections):
            col_obj = self.collections[index]
            return col_obj.name if hasattr(col_obj, 'name') else str(col_obj)
        return None

    def list_collections(self):
        """列出所有collections"""
        print("="*60)
        print("📋 Collections 列表")
        print("="*60)

        if not self.collections:
            print("❌ 没有找到任何 collections")
            return

        for i, col_obj in enumerate(self.collections, 1):
            try:
                # 获取实际的collection名称
                col_name = col_obj.name if hasattr(col_obj, 'name') else str(col_obj)
                col = self.client.get_collection(col_name)
                count = col.count()
                print(f"{i}. {col_name} ({count} 文档)")
            except Exception as e:
                print(f"{i}. {col_obj} (获取失败: {e})")

        print()

    def show_collection_stats(self, collection_name=None):
        """显示collection统计信息"""
        if not collection_name:
            # 让用户选择collection
            self.list_collections()
            idx = input("请选择 collection 编号: ").strip()
            try:
                idx = int(idx) - 1
                collection_name = self._get_collection_name(idx)
                if not collection_name:
                    print("❌ 无效选择")
                    return
            except ValueError:
                print("❌ 请输入有效数字")
                return

        try:
            col = self.client.get_collection(collection_name)
            count = col.count()

            print(f"\n{'='*60}")
            print(f"📊 Collection: {collection_name}")
            print(f"{'='*60}")
            print(f"文档总数: {count}")

            # 获取metadata统计
            results = col.get(include=['metadatas', 'documents'])

            # 统计文件来源
            sources = Counter()
            doc_lengths = []

            for meta in results['metadatas']:
                source = meta.get('source', 'unknown')
                file_name = Path(source).name if source != 'unknown' else 'unknown'
                sources[file_name] += 1

            for doc in results['documents']:
                doc_lengths.append(len(doc))

            print(f"\n📁 文件分布:")
            for file_name, count in sources.most_common():
                print(f"  • {file_name}: {count} 块")

            if doc_lengths:
                print(f"\n📏 文档长度统计:")
                print(f"  • 平均: {sum(doc_lengths)/len(doc_lengths):.0f} 字符")
                print(f"  • 最短: {min(doc_lengths)} 字符")
                print(f"  • 最长: {max(doc_lengths)} 字符")

            print()

        except Exception as e:
            print(f"❌ 获取统计失败: {e}\n")

    def show_documents(self, collection_name=None, limit=10):
        """显示文档内容"""
        if not collection_name:
            self.list_collections()
            idx = input("请选择 collection 编号: ").strip()
            try:
                idx = int(idx) - 1
                collection_name = self._get_collection_name(idx)
                if not collection_name:
                    print("❌ 无效选择")
                    return
            except ValueError:
                print("❌ 请输入有效数字")
                return

        try:
            col = self.client.get_collection(collection_name)
            count = col.count()

            # 让用户选择查看数量
            print(f"\n此 collection 有 {count} 个文档")
            try:
                limit_input = input(f"查看前几个文档 (默认{limit}): ").strip()
                if limit_input:
                    limit = int(limit_input)
            except ValueError:
                pass

            results = col.get(include=['documents', 'metadatas'], limit=limit)

            print(f"\n{'='*60}")
            print(f"📄 文档内容 (前{limit}个)")
            print(f"{'='*60}")

            for i, (doc, meta) in enumerate(zip(results['documents'], results['metadatas']), 1):
                source = meta.get('source', 'unknown')
                file_name = Path(source).name if source != 'unknown' else 'unknown'
                preview = doc[:150].replace('\n', ' ')

                print(f"\n[{i}] {file_name}")
                print(f"    路径: {source}")
                print(f"    内容: {preview}{'...' if len(doc) > 150 else ''}")

            print()

        except Exception as e:
            print(f"❌ 获取文档失败: {e}\n")

    def search_similar(self, collection_name=None, query_text=None, n_results=5):
        """相似度搜索"""
        if not query_text:
            query_text = input("\n请输入搜索查询: ").strip()
            if not query_text:
                print("❌ 查询不能为空")
                return

        if not collection_name:
            self.list_collections()
            idx = input("请选择 collection 编号: ").strip()
            try:
                idx = int(idx) - 1
                collection_name = self._get_collection_name(idx)
                if not collection_name:
                    print("❌ 无效选择")
                    return
            except ValueError:
                print("❌ 请输入有效数字")
                return

        try:
            # 尝试使用本地embedding
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
                embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2"
                )
                print("✓ 使用本地 embedding 模型")
                query_embedding = embeddings.embed_query(query_text)

                col = self.client.get_collection(collection_name)
                results = col.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    include=['documents', 'metadatas', 'distances']
                )

                print(f"\n{'='*60}")
                print(f"🔎 搜索结果: '{query_text}'")
                print(f"{'='*60}")

                for i, (doc, meta, dist) in enumerate(zip(
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                ), 1):

                    source = meta.get('source', 'unknown')
                    file_name = Path(source).name if source != 'unknown' else 'unknown'
                    preview = doc[:200].replace('\n', ' ')
                    similarity = 1 - dist if dist <= 1 else dist

                    print(f"\n[{i}] {file_name}")
                    print(f"    相似度: {similarity:.4f}")
                    print(f"    内容: {preview}{'...' if len(doc) > 200 else ''}")

                print()

            except ImportError:
                print("❌ 需要安装 langchain-huggingface 和 sentence-transformers")
                print("  pip install langchain-huggingface sentence-transformers")

        except Exception as e:
            print(f"❌ 搜索失败: {e}\n")

    def filter_by_file(self, collection_name=None):
        """按文件过滤"""
        if not collection_name:
            self.list_collections()
            idx = input("请选择 collection 编号: ").strip()
            try:
                idx = int(idx) - 1
                collection_name = self._get_collection_name(idx)
                if not collection_name:
                    print("❌ 无效选择")
                    return
            except ValueError:
                print("❌ 请输入有效数字")
                return

        try:
            col = self.client.get_collection(collection_name)

            # 获取所有文件
            results = col.get(include=['metadatas'])
            files = set()
            for meta in results['metadatas']:
                source = meta.get('source', '')
                if source:
                    file_name = Path(source).name
                    files.add(file_name)

            print(f"\n此 collection 中的文件:")
            for i, file_name in enumerate(sorted(files), 1):
                print(f"  {i}. {file_name}")

            # 让用户选择文件
            idx = input("\n请选择文件编号: ").strip()
            try:
                idx = int(idx) - 1
                selected_file = sorted(files)[idx] if 0 <= idx < len(files) else None
                if not selected_file:
                    print("❌ 无效选择")
                    return
            except (ValueError, IndexError):
                print("❌ 请输入有效数字")
                return

            # 获取该文件的所有文档
            all_results = col.get(include=['documents', 'metadatas'])
            filtered_docs = []
            filtered_metas = []

            for doc, meta in zip(all_results['documents'], all_results['metadatas']):
                source = meta.get('source', '')
                if source and Path(source).name == selected_file:
                    filtered_docs.append(doc)
                    filtered_metas.append(meta)

            print(f"\n{'='*60}")
            print(f"📁 文件: {selected_file} ({len(filtered_docs)} 块)")
            print(f"{'='*60}")

            for i, (doc, meta) in enumerate(zip(filtered_docs, filtered_metas), 1):
                preview = doc[:150].replace('\n', ' ')
                print(f"\n[{i}] {preview}{'...' if len(doc) > 150 else ''}")

            print()

        except Exception as e:
            print(f"❌ 过滤失败: {e}\n")

    def show_metadata_fields(self, collection_name=None):
        """显示metadata字段信息"""
        if not collection_name:
            self.list_collections()
            idx = input("请选择 collection 编号: ").strip()
            try:
                idx = int(idx) - 1
                collection_name = self._get_collection_name(idx)
                if not collection_name:
                    print("❌ 无效选择")
                    return
            except ValueError:
                print("❌ 请输入有效数字")
                return

        try:
            col = self.client.get_collection(collection_name)
            results = col.get(include=['metadatas'], limit=10)

            print(f"\n{'='*60}")
            print(f"🔍 Collection: {collection_name}")
            print(f"Metadata 字段示例")
            print(f"{'='*60}")

            all_fields = set()
            for meta in results['metadatas']:
                all_fields.update(meta.keys())

            if all_fields:
                print(f"\n所有字段: {', '.join(sorted(all_fields))}")
                print(f"\n前10个文档的 metadata:")
                for i, meta in enumerate(results['metadatas'], 1):
                    print(f"\n[{i}]")
                    for key, value in meta.items():
                        print(f"  {key}: {value}")
            else:
                print("没有找到 metadata")

            print()

        except Exception as e:
            print(f"❌ 获取字段失败: {e}\n")

    def delete_collection(self, collection_name=None):
        """删除指定的 collection"""
        if not collection_name:
            # 让用户选择要删除的 collection
            self.list_collections()
            idx = input("请选择要删除的 collection 编号: ").strip()
            try:
                idx = int(idx) - 1
                collection_name = self._get_collection_name(idx)
                if not collection_name:
                    print("❌ 无效选择")
                    return
            except ValueError:
                print("❌ 请输入有效数字")
                return

        try:
            # 确认删除
            col = self.client.get_collection(collection_name)
            count = col.count()

            print(f"\n{'='*60}")
            print(f"⚠️  确认删除 Collection")
            print(f"{'='*60}")
            print(f"Collection: {collection_name}")
            print(f"文档数: {count}")
            print("\n⚠️  此操作不可撤销！")

            confirm = input(f"\n确定要删除 '{collection_name}' 吗？(输入 'yes' 确认): ").strip()

            if confirm.lower() != 'yes':
                print("已取消删除")
                return

            # 执行删除
            self.client.delete_collection(collection_name)
            print(f"\n✅ 已成功删除 collection: {collection_name}")

            # 刷新 collections 列表
            self.collections = self.client.list_collections()
            print(f"剩余 collections: {len(self.collections)} 个")

        except Exception as e:
            print(f"❌ 删除失败: {e}\n")

    def run(self):
        """运行交互式查询"""
        while True:
            print("\n" + "="*60)
            print("🔍 ChromaDB 查询工具")
            print("="*60)
            print("1. 查看所有 Collections")
            print("2. Collection 统计信息")
            print("3. 查看文档内容")
            print("4. 相似度搜索")
            print("5. 按文件过滤")
            print("6. 查看 Metadata 字段")
            print("7. 删除 Collection")
            print("0. 退出")
            print("="*60)

            choice = input("\n请选择操作 (0-7): ").strip()

            if choice == '0':
                print("\n👋 再见!")
                break
            elif choice == '1':
                self.list_collections()
            elif choice == '2':
                self.show_collection_stats()
            elif choice == '3':
                self.show_documents()
            elif choice == '4':
                self.search_similar()
            elif choice == '5':
                self.filter_by_file()
            elif choice == '6':
                self.show_metadata_fields()
            elif choice == '7':
                self.delete_collection()
            else:
                print("❌ 无效选择，请输入 0-7 之间的数字")

def main():
    print("\n" + "="*60)
    print("🚀 欢迎使用 ChromaDB 查询工具")
    print("="*60)

    # 允许用户自定义连接
    host = input("Chroma 主机 (默认 localhost): ").strip() or "localhost"

    try:
        port = int(input("Chroma 端口 (默认 9000): ").strip() or "9000")
    except ValueError:
        print("❌ 端口无效，使用默认 9000")
        port = 9000

    # 创建查询工具并运行
    tool = ChromaQueryTool(host=host, port=port)
    tool.run()

if __name__ == "__main__":
    main()
