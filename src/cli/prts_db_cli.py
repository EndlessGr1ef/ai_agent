#!/usr/bin/env python3
"""
PRTS ChromaDB 统一管理 CLI
A unified interactive CLI for ChromaDB management with PRTS theme

Features:
- Query: List collections, stats, similarity search
- Ingest: Import raw/distilled documents with auto is_distilled tagging
- Distill: Call distill_knowledge.py to generate distilled docs
- Delete: Collection management
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path
from typing import Optional

# Import existing tools
from src.cli.chroma_query_tool import ChromaQueryTool


class PRTSDBManager:
    """Main manager class for PRTS ChromaDB operations"""
    
    def __init__(self, host: str = "localhost", port: int = 9000):
        """Initialize PRTS DB Manager"""
        self.host = host
        self.port = port
        self.query_tool = None
        
        print("\n" + "="*60)
        print("[PRTS]$ ChromaDB 管理工具")
        print("[PRTS]$ PRTS Tactical Database Management System")
        print("="*60)
        
        # Initialize query tool
        try:
            self.query_tool = ChromaQueryTool(host=host, port=port)
        except Exception as e:
            print(f"[ERROR] 无法连接到 ChromaDB: {e}")
            print("[INFO] 请确保 ChromaDB 服务正在运行")
            sys.exit(1)
    
    def show_main_menu(self):
        """Display main menu"""
        print("\n" + "="*60)
        print("[PRTS]$ 主菜单 Main Menu")
        print("="*60)
        print("1. 查询 Query - 查看Collections、统计、搜索")
        print("2. 入库 Ingest - 原始/提炼文档批量导入")
        print("3. 提炼 Distill - 生成提炼版文档")
        print("4. 删除 Delete - Collection管理")
        print("0. 退出 Exit")
        print("="*60)
    
    def query_menu(self):
        """Query submenu - reuse ChromaQueryTool"""
        while True:
            print("\n" + "="*60)
            print("[PRTS]$ 查询菜单 Query Menu")
            print("="*60)
            print("1. 查看所有 Collections")
            print("2. Collection 统计信息")
            print("3. 查看文档内容")
            print("4. 相似度搜索")
            print("5. 按文件过滤")
            print("6. 查看 Metadata 字段")
            print("0. 返回主菜单")
            print("="*60)
            
            choice = input("\n[PRTS]$ 请选择操作 (0-6): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                self.query_tool.list_collections()
            elif choice == '2':
                self.query_tool.show_collection_stats()
            elif choice == '3':
                self.query_tool.show_documents()
            elif choice == '4':
                self.query_tool.search_similar()
            elif choice == '5':
                self.query_tool.filter_by_file()
            elif choice == '6':
                self.query_tool.show_metadata_fields()
            else:
                print("[WARN] 无效选择，请输入 0-6 之间的数字")
    
    def ingest_menu(self):
        """Ingest submenu - handle raw/distilled/unified modes"""
        while True:
            print("\n" + "="*60)
            print("[PRTS]$ 入库菜单 Ingest Menu")
            print("="*60)
            print("1. 原始文档入库 (is_distilled=False)")
            print("2. 提炼文档入库 (is_distilled=True)")
            print("3. 统一入库 (原始+提炼 -> 同一Collection)")
            print("0. 返回主菜单")
            print("="*60)
            
            choice = input("\n[PRTS]$ 请选择操作 (0-3): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                self._ingest_single_mode(is_distilled=False)
            elif choice == '2':
                self._ingest_single_mode(is_distilled=True)
            elif choice == '3':
                self._ingest_unified_mode()
            else:
                print("[WARN] 无效选择，请输入 0-3 之间的数字")
    
    def _ingest_single_mode(self, is_distilled: bool):
        """Handle single mode ingest (raw or distilled)"""
        mode_name = "提炼版" if is_distilled else "原始版"
        default_dir = "docs/prts_distilled" if is_distilled else "docs/prts"
        
        print(f"\n[INFO] {mode_name}文档入库")
        print("="*60)
        
        # Get input directory
        docs_dir = input(f"文档目录 (默认: {default_dir}): ").strip() or default_dir
        if not os.path.exists(docs_dir):
            print(f"[ERROR] 目录不存在: {docs_dir}")
            return
        
        # Get collection name
        default_collection = "prts_wiki"
        collection = input(f"Collection 名称 (默认: {default_collection}): ").strip() or default_collection
        
        # Get chunk settings
        chunk_size = input("Chunk size (默认: 1500): ").strip()
        chunk_size = int(chunk_size) if chunk_size else 1500
        
        chunk_overlap = input("Chunk overlap (默认: 300): ").strip()
        chunk_overlap = int(chunk_overlap) if chunk_overlap else 300
        
        # Confirm
        print(f"\n[INFO] 即将执行:")
        print(f"  文档目录: {docs_dir}")
        print(f"  Collection: {collection}")
        print(f"  is_distilled: {is_distilled}")
        print(f"  Chunk size: {chunk_size}, Overlap: {chunk_overlap}")
        
        confirm = input("\n确认执行? (yes/n): ").strip().lower()
        if confirm != 'yes':
            print("[INFO] 已取消")
            return
        
        # Execute ingest
        print(f"\n[STATUS] 开始入库...")
        try:
            cmd = [
                sys.executable, "-m", "src.data.ingestion.ingest_md",
                "--docs-dir", docs_dir,
                "--collection", collection,
                "--chroma-host", self.host,
                "--chroma-port", str(self.port),
                "--chunk-size", str(chunk_size),
                "--chunk-overlap", str(chunk_overlap)
            ]
            
            if is_distilled:
                # Add --is-distilled flag
                cmd.append("--is-distilled")
            
            result = subprocess.run(cmd)
            
            if result.returncode == 0:
                print(f"\n[STATUS] ✅ 入库完成!")
            else:
                print(f"\n[ERROR] 入库失败，返回码: {result.returncode}")
        except Exception as e:
            print(f"[ERROR] 执行失败: {e}")
    
    def _ingest_unified_mode(self):
        """Handle unified mode ingest (raw + distilled)"""
        print("\n[INFO] 统一入库模式 (原始+提炼)")
        print("="*60)
        
        # Get base directories
        raw_dir = input("原始文档目录 (默认: docs/prts/干员): ").strip() or "docs/prts/干员"
        distilled_dir = input("提炼文档目录 (默认: docs/prts_distilled/干员): ").strip() or "docs/prts_distilled/干员"
        
        if not os.path.exists(raw_dir):
            print(f"[ERROR] 原始目录不存在: {raw_dir}")
            return
        if not os.path.exists(distilled_dir):
            print(f"[WARN] 提炼目录不存在: {distilled_dir}")
            print("[INFO] 将仅入库原始版")
        
        # Get collection name
        collection = input("Collection 名称 (默认: prts_wiki): ").strip() or "prts_wiki"
        
        # Confirm
        print(f"\n[INFO] 即将执行:")
        print(f"  原始版: {raw_dir} -> {collection} (is_distilled=False)")
        if os.path.exists(distilled_dir):
            print(f"  提炼版: {distilled_dir} -> {collection} (is_distilled=True)")
        
        confirm = input("\n确认执行? (yes/n): ").strip().lower()
        if confirm != 'yes':
            print("[INFO] 已取消")
            return
        
        # Execute ingest for raw
        print(f"\n[STATUS] 步骤 1/2: 入库原始版...")
        try:
            cmd_raw = [
                sys.executable, "-m", "src.data.ingestion.ingest_md",
                "--docs-dir", raw_dir,
                "--collection", collection,
                "--chroma-host", self.host,
                "--chroma-port", str(self.port)
            ]
            result_raw = subprocess.run(cmd_raw)
            
            if result_raw.returncode == 0:
                print("[STATUS] ✅ 原始版入库完成")
            else:
                print(f"[ERROR] 原始版入库失败，返回码: {result_raw.returncode}")
                return
        except Exception as e:
            print(f"[ERROR] 原始版入库失败: {e}")
            return
        
        # Execute ingest for distilled
        if os.path.exists(distilled_dir):
            print(f"\n[STATUS] 步骤 2/2: 入库提炼版...")
            try:
                cmd_distilled = [
                    sys.executable, "-m", "src.data.ingestion.ingest_md",
                    "--docs-dir", distilled_dir,
                    "--collection", collection,
                    "--chroma-host", self.host,
                    "--chroma-port", str(self.port),
                    "--is-distilled"
                ]
                result_distilled = subprocess.run(cmd_distilled)
                
                if result_distilled.returncode == 0:
                    print("[STATUS] ✅ 提炼版入库完成")
                else:
                    print(f"[ERROR] 提炼版入库失败，返回码: {result_distilled.returncode}")
            except Exception as e:
                print(f"[ERROR] 提炼版入库失败: {e}")
        
        print(f"\n[STATUS] ✅ 统一入库完成!")
    
    def distill_menu(self):
        """Distill submenu - call distill_knowledge.py"""
        print("\n" + "="*60)
        print("[PRTS]$ 提炼菜单 Distill Menu")
        print("="*60)
        print("[INFO] 调用 LLM 生成提炼版文档")
        print("="*60)
        
        # Get input/output directories
        input_dir = input("原始文档目录 (默认: docs/prts): ").strip() or "docs/prts"
        if not os.path.exists(input_dir):
            print(f"[ERROR] 目录不存在: {input_dir}")
            return
        
        output_dir = input("提炼输出目录 (默认: docs/prts_distilled): ").strip() or "docs/prts_distilled"
        
        # Get concurrency
        concurrency = input("并发数 (默认: 8): ").strip()
        concurrency = int(concurrency) if concurrency else 8
        
        # Optional limit for testing
        limit = input("限制处理文件数 (默认: 0=全部): ").strip()
        limit = int(limit) if limit else 0
        
        # Confirm
        print(f"\n[INFO] 即将执行:")
        print(f"  输入目录: {input_dir}")
        print(f"  输出目录: {output_dir}")
        print(f"  并发数: {concurrency}")
        if limit > 0:
            print(f"  限制文件数: {limit}")
        
        confirm = input("\n确认执行? (yes/n): ").strip().lower()
        if confirm != 'yes':
            print("[INFO] 已取消")
            return
        
        # Execute distillation
        print(f"\n[STATUS] 开始提炼...")
        try:
            cmd = [
                sys.executable, "-m", "src.data.distillation.distill_knowledge",
                "--input-dir", input_dir,
                "--output-dir", output_dir,
                "--concurrency", str(concurrency)
            ]
            
            if limit > 0:
                cmd.extend(["--limit", str(limit)])
            
            result = subprocess.run(cmd)
            
            if result.returncode == 0:
                print(f"\n[STATUS] ✅ 提炼完成!")
                
                # Ask if user wants to ingest now
                ingest_now = input("\n是否立即入库提炼版文档? (yes/n): ").strip().lower()
                if ingest_now == 'yes':
                    print("\n[INFO] 跳转到入库菜单...")
                    self._ingest_single_mode(is_distilled=True)
            else:
                print(f"\n[ERROR] 提炼失败，返回码: {result.returncode}")
        except Exception as e:
            print(f"[ERROR] 执行失败: {e}")
    
    def delete_menu(self):
        """Delete submenu - collection management"""
        print("\n" + "="*60)
        print("[PRTS]$ 删除管理 Delete Management")
        print("="*60)
        
        # List collections
        self.query_tool.list_collections()
        
        if not self.query_tool.collections:
            print("[INFO] 没有可删除的 collections")
            return
        
        # Get collection to delete
        idx = input("\n请选择要删除的 collection 编号 (0=取消): ").strip()
        
        if idx == '0':
            print("[INFO] 已取消")
            return
        
        try:
            idx = int(idx) - 1
            collection_name = self.query_tool._get_collection_name(idx)
            if not collection_name:
                print("[ERROR] 无效选择")
                return
        except ValueError:
            print("[ERROR] 请输入有效数字")
            return
        
        # Get collection info
        try:
            col = self.query_tool.client.get_collection(collection_name)
            count = col.count()
            
            print(f"\n{'='*60}")
            print(f"⚠️  确认删除 Collection")
            print(f"{'='*60}")
            print(f"Collection: {collection_name}")
            print(f"文档数: {count}")
            print("\n⚠️  此操作不可撤销!")
            
            confirm = input(f"\n确定要删除 '{collection_name}' 吗？(输入 'yes' 确认): ").strip()
            
            if confirm.lower() != 'yes':
                print("[INFO] 已取消删除")
                return
            
            # Execute deletion
            self.query_tool.client.delete_collection(collection_name)
            print(f"\n[STATUS] ✅ 已成功删除 collection: {collection_name}")
            
            # Refresh collections list
            self.query_tool.collections = self.query_tool.client.list_collections()
            print(f"[INFO] 剩余 collections: {len(self.query_tool.collections)} 个")
            
        except Exception as e:
            print(f"[ERROR] 删除失败: {e}")
    
    def run(self):
        """Main loop"""
        while True:
            self.show_main_menu()
            choice = input("\n[PRTS]$ 请选择操作 (0-4): ").strip()
            
            if choice == '0':
                print("\n[PRTS]$ 系统关闭。再见，博士。")
                print("[PRTS]$ System shutting down. Goodbye, Doctor.\n")
                break
            elif choice == '1':
                self.query_menu()
            elif choice == '2':
                self.ingest_menu()
            elif choice == '3':
                self.distill_menu()
            elif choice == '4':
                self.delete_menu()
            else:
                print("[WARN] 无效选择，请输入 0-4 之间的数字")


def main():
    """Entry point"""
    parser = argparse.ArgumentParser(
        description='PRTS ChromaDB Unified Management CLI',
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
    
    args = parser.parse_args()
    
    # Create and run manager
    manager = PRTSDBManager(host=args.host, port=args.port)
    manager.run()


if __name__ == "__main__":
    main()
