#!/usr/bin/env python3
"""
Clean up character files and identify missing operators.

This script:
1. Renames files with Wiki suffix to proper names
2. Removes duplicate/system files
3. Reports actual character count vs expected count
"""

import os
from pathlib import Path
import shutil


def clean_character_files(dry_run=True):
    """Clean up character directory."""
    char_dir = Path("docs/prts/干员")
    
    if not char_dir.exists():
        print(f"❌ Directory not found: {char_dir}")
        return
    
    print("="*60)
    print("🔍 扫描干员目录...")
    print("="*60)
    
    # Find files with Wiki suffix
    wiki_files = list(char_dir.glob("*PRTS*")) + list(char_dir.glob("*Wiki*"))
    
    print(f"\n发现 {len(wiki_files)} 个异常文件（带 PRTS/Wiki 后缀）:")
    
    for file_path in wiki_files:
        # Extract operator name from filename
        filename = file_path.name
        
        # Remove the Wiki suffix
        if " - PRTS - " in filename:
            clean_name = filename.split(" - PRTS - ")[0] + ".md"
        else:
            clean_name = filename
        
        new_path = char_dir / clean_name
        
        print(f"\n  原文件: {filename}")
        print(f"  新文件: {clean_name}")
        
        # Check if clean version already exists
        if new_path.exists() and new_path != file_path:
            print(f"  ⚠️  目标文件已存在，将删除重复文件")
            if not dry_run:
                file_path.unlink()
                print(f"  ✅ 已删除重复文件")
        else:
            print(f"  → 将重命名")
            if not dry_run:
                file_path.rename(new_path)
                print(f"  ✅ 已重命名")
    
    # Find system files
    system_keywords = [
        "泰拉大陆调查团", "公招计算", "异常效果", 
        "PRTS", "如何帮助", "专属干员"
    ]
    
    print(f"\n" + "="*60)
    print("🔍 检查系统页面...")
    print("="*60)
    
    system_files = []
    for file_path in char_dir.glob("*.md"):
        filename = file_path.stem
        if any(keyword in filename for keyword in system_keywords):
            system_files.append(file_path)
    
    if system_files:
        print(f"\n发现 {len(system_files)} 个系统页面（非干员）:")
        for file_path in system_files:
            print(f"  - {file_path.name}")
            if not dry_run:
                # Move to backup directory
                backup_dir = Path("docs/prts/系统页面")
                backup_dir.mkdir(exist_ok=True)
                shutil.move(str(file_path), str(backup_dir / file_path.name))
                print(f"    ✅ 已移动到 {backup_dir}")
    
    # Count final results
    print(f"\n" + "="*60)
    print("📊 统计结果")
    print("="*60)
    
    final_count = len(list(char_dir.glob("*.md")))
    print(f"\n当前干员文件数: {final_count}")
    print(f"PRTS Wiki 显示: ~400 个干员")
    print(f"差距: {400 - final_count} 个")
    
    if 400 - final_count > 0:
        print(f"\n💡 建议:")
        print(f"   1. 运行增量爬取补充缺失干员:")
        print(f"      python scrape_prts.py --type characters")
        print(f"   2. 这将自动跳过已有文件，只爬取新增干员")
    
    if dry_run:
        print(f"\n⚠️  这是试运行模式，没有实际修改文件")
        print(f"   要执行清理，请运行: python clean_characters.py --execute")


if __name__ == "__main__":
    import sys
    
    dry_run = "--execute" not in sys.argv
    
    if dry_run:
        print("\n🔍 试运行模式（不会修改文件）")
        print("="*60)
    else:
        print("\n⚡ 执行模式（将修改文件）")
        print("="*60)
        confirm = input("\n确认执行清理操作？(y/n): ").strip().lower()
        if confirm != 'y':
            print("❌ 已取消")
            sys.exit(0)
    
    clean_character_files(dry_run=dry_run)

