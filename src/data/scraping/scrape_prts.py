#!/usr/bin/env python3
"""
Command-line interface for PRTS Wiki scraping.

This script provides a convenient CLI for scraping PRTS Wiki content
(character and story) and ingesting it into ChromaDB for RAG applications.
"""

import asyncio
import logging
import sys
import os
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.rag.scrapers.scraper_factory import ScraperFactory
from src.rag.scrapers.story_scraper import StoryScraper
from src.rag.scrapers.character_scraper import CharacterScraper
from src.rag.scrapers.prts_wiki_scraper import PRTSWikiScraper
from src.utils.prts_verifier import PRTSVerifier


# 固定的剧情URL（如果用户选择剧情但没有提供URL）
STORY_LIST_URL = "https://prts.wiki/w/剧情一览"

# 固定的干员URL（如果用户选择干员但没有提供URL）
CHARACTER_LIST_URL = "https://prts.wiki/w/干员一览"


def display_banner():
    """显示欢迎横幅"""
    banner = """
╔════════════════════════════════════════════════════════╗
║           PRTS Wiki 爬虫 - 内容爬取工具                 ║
║                  版本 2.0.0                             ║
╚════════════════════════════════════════════════════════╝
"""
    print(banner)


def interactive_selection() -> tuple[str, str, Optional[int], str]:
    """
    交互式选择内容类型

    Returns:
        tuple: (内容类型, URL, 最大页数, 输出目录)
    """
    print("\n请选择要爬取的内容类型：\n")

    print("1️⃣  干员信息")
    print("   - 从干员一览页面开始爬取")
    print("   - 获取所有干员的详细信息")
    print("   - 包括技能、天赋、属性等数据\n")

    print("2️⃣  剧情内容")
    print("   - 从剧情一览页面开始爬取")
    print("   - 获取主线、角色、活动等剧情")
    print("   - 包括对话、旁白、章节结构\n")

    print("3️⃣  全部内容")
    print("   - 先爬取干员信息")
    print("   - 再爬取剧情内容")
    print("   - 完整的PRTS Wiki内容\n")

    while True:
        try:
            choice = input("请输入选择 (1/2/3) [默认: 1]: ").strip()

            if not choice:
                choice = '1'

            if choice not in ['1', '2', '3']:
                print("❌ 无效选择，请输入 1、2 或 3")
                continue

            break

        except KeyboardInterrupt:
            print("\n\n👋 操作已取消")
            sys.exit(0)

    # 根据选择确定内容类型
    if choice == '1':
        content_type = 'character'
        url = CHARACTER_LIST_URL
        print(f"\n✅ 已选择: 干员信息")
        print(f"🌐 目标URL: {url}")
    elif choice == '2':
        content_type = 'story'
        url = STORY_LIST_URL
        print(f"\n✅ 已选择: 剧情内容")
        print(f"🌐 目标URL: {url}")
    else:  # choice == '3'
        content_type = 'all'
        url = None  # 需要先爬干员再爬剧情
        print(f"\n✅ 已选择: 全部内容")
        print("📋 将按顺序爬取：干员 → 剧情")

    # 询问最大页数/章节数
    print("\n" + "="*60)
    while True:
        try:
            max_input = input(
                f"最大爬取数量 [默认: 无限, 输入数字限制]: "
            ).strip()

            if not max_input:
                max_pages = None
            else:
                max_pages = int(max_input)

            break

        except ValueError:
            print("❌ 请输入有效数字")
        except KeyboardInterrupt:
            print("\n\n👋 操作已取消")
            sys.exit(0)

    # 询问输出目录
    print("\n" + "="*60)
    output_dir = input(
        f"输出目录 [默认: docs/prts]: "
    ).strip()

    if not output_dir:
        output_dir = "docs/prts"

    print(f"\n📁 输出目录: {output_dir}")

    # 询问并发数（仅对剧情爬取）
    print("\n" + "="*60)
    if content_type == 'story' or content_type == 'all':
        print("⚙️  并发设置（剧情爬取）:")
        print("   - 并发可以大幅提升抓取速度")
        print("   - 建议设置5-8，避免被反爬虫检测")
        print("   - 串行模式速度慢但更稳定\n")

        while True:
            try:
                concurrent_input = input(
                    f"最大并发数 [默认: 5, 输入 0 使用串行模式]: "
                ).strip()

                if not concurrent_input:
                    max_concurrent = 5
                else:
                    max_concurrent = int(concurrent_input)

                if max_concurrent < 0:
                    print("❌ 并发数不能为负数")
                    continue
                if max_concurrent == 0:
                    print("✅ 使用串行模式")
                    max_concurrent = 1  # 串行模式实际上就是并发数1
                elif max_concurrent > 10:
                    print("⚠️  警告: 并发数过高可能导致被反爬虫检测")

                break

            except ValueError:
                print("❌ 请输入有效数字")
            except KeyboardInterrupt:
                print("\n\n👋 操作已取消")
                sys.exit(0)

        print(f"\n⚙️  并发设置: {max_concurrent}")
    else:
        max_concurrent = 5  # 干员爬取默认5

    print("\n" + "="*60)
    print("🚀 准备开始爬取...")
    print("="*60 + "\n")

    return content_type, url, max_pages, output_dir, max_concurrent


async def scrape_characters(url: str, max_pages: Optional[int], output_dir: str, no_js_render: bool = False, skip_verification: bool = False):
    """爬取干员信息"""
    print("📋 正在初始化干员爬虫...")

    scraper = CharacterScraper(output_dir=output_dir, use_js_renderer=not no_js_render)

    # Verification stage (unless explicitly skipped)
    character_links_to_scrape = []
    
    if not skip_verification:
        print("\n" + "="*60)
        print("🔍 验证阶段：检查是否有新内容...")
        print("="*60 + "\n")
        
        verifier = PRTSVerifier(output_dir=output_dir)
        report = await verifier.verify_characters(verbose=False)
        
        # Display PRTS-style report
        verifier.display_prts_report(report)
        
        # Check if there are missing items
        if not report['missing_items']:
            print("\n[INFO] 本地内容已是最新，无需爬取")
            print("[PRTS]$ 任务完成，博士\n")
            return
        
        # Ask user confirmation
        print(f"\n[PRTS]$ 发现 {len(report['missing_items'])} 个新干员")
        confirm = input("是否继续增量爬取？(y/n) [默认: y]: ").strip().lower()
        
        if confirm and confirm != 'y':
            print("\n[INFO] 已取消爬取")
            return
        
        # Only scrape missing items
        character_links_to_scrape = [item['url'] for item in report['missing_items']]
        print(f"\n✅ 将爬取 {len(character_links_to_scrape)} 个缺失的干员")
        print("="*60 + "\n")
    else:
        print("🔍 正在提取干员链接...")
        # 获取所有干员链接
        character_links_to_scrape = await scraper._extract_all_character_links_with_pagination(url)

    if max_pages and not skip_verification:
        # 如果指定了最大页数，限制链接数量
        links_per_page = 15
        max_links = max_pages * links_per_page
        character_links_to_scrape = character_links_to_scrape[:max_links]
        print(f"⚠️  已限制数量：{len(character_links_to_scrape)} 个干员 (来自前{max_pages}页)")

    if not character_links_to_scrape:
        print("❌ 未找到任何需要爬取的干员链接")
        return

    # 批量爬取
    print(f"\n🚀 开始{'增量' if not skip_verification else ''}爬取干员信息...")
    print(f"📊 总数: {len(character_links_to_scrape)}")

    results = []
    for i, link in enumerate(character_links_to_scrape, 1):
        print(f"\r⏳ 进度: {i}/{len(character_links_to_scrape)} - {link[:50]}...", end='', flush=True)

        try:
            # Use extract_single_character which handles file existence check
            result = await scraper.extract_single_character(link)
            results.append(result)
        except Exception as e:
            results.append({
                'success': False,
                'url': link,
                'error': str(e)
            })

        # 添加延迟
        await asyncio.sleep(scraper.delay_range[0])

    print("\n")

    # 统计结果
    success_count = sum(1 for r in results if r.get('success'))
    skipped_count = sum(1 for r in results if r.get('skipped'))
    failed_count = len(results) - success_count - skipped_count

    print("\n" + "="*60)
    print("🎉 干员爬取完成!")
    print("="*60)
    print(f"✅ 成功: {success_count}")
    print(f"⏭️  跳过 (已存在): {skipped_count}")
    print(f"❌ 失败: {failed_count}")
    print(f"📈 成功率: {success_count/len(results)*100:.1f}%")
    print(f"📁 输出目录: {scraper.output_dir}/")
    print("="*60 + "\n")


async def scrape_stories(url: str, max_stories: Optional[int], output_dir: str, max_concurrent: int = 5, skip_verification: bool = False):
    """爬取剧情内容"""
    print("📋 正在初始化剧情爬虫...")

    # 检查是否使用串行模式
    use_parallel = max_concurrent > 1
    if use_parallel:
        print(f"🚀 使用并发模式 (并发数: {max_concurrent})")
        scraper = StoryScraper(output_dir=output_dir, max_concurrent=max_concurrent)
    else:
        print("🔄 使用串行模式")
        scraper = StoryScraper(output_dir=output_dir, max_concurrent=1)

    # Verification stage (unless explicitly skipped)
    story_links_to_scrape = []
    
    if not skip_verification:
        print("\n" + "="*60)
        print("🔍 验证阶段：检查是否有新内容...")
        print("="*60 + "\n")
        
        verifier = PRTSVerifier(output_dir=output_dir)
        report = await verifier.verify_stories(verbose=False)
        
        # Display PRTS-style report
        verifier.display_prts_report(report)
        
        # Check if there are missing items
        if not report['missing_items']:
            print("\n[INFO] 本地内容已是最新，无需爬取")
            print("[PRTS]$ 任务完成，博士\n")
            return
        
        # Ask user confirmation
        print(f"\n[PRTS]$ 发现 {len(report['missing_items'])} 个新剧情")
        confirm = input("是否继续增量爬取？(y/n) [默认: y]: ").strip().lower()
        
        if confirm and confirm != 'y':
            print("\n[INFO] 已取消爬取")
            return
        
        # Only scrape missing items (convert to format expected by scraper)
        story_links_to_scrape = [
            {'url': item['url'], 'title': item['name']} 
            for item in report['missing_items']
        ]
        print(f"\n✅ 将爬取 {len(story_links_to_scrape)} 个缺失的剧情")
        print("="*60 + "\n")
    else:
        print("🔍 正在提取剧情链接...")
        # 获取所有剧情链接（默认启用分类功能）
        story_links_to_scrape = await scraper.scrape_story_list(url, with_categories=True)

    if max_stories and not skip_verification:
        story_links_to_scrape = story_links_to_scrape[:max_stories]
        print(f"⚠️  已限制数量：{len(story_links_to_scrape)} 个剧情")

    if not story_links_to_scrape:
        print("❌ 未找到任何需要爬取的剧情链接")
        return

    # 批量爬取
    print(f"\n🚀 开始{'增量' if not skip_verification else ''}爬取剧情内容...")
    print(f"📊 总数: {len(story_links_to_scrape)}")
    if use_parallel:
        print(f"⚡ 并发模式 - 同时处理 {max_concurrent} 个页面")
    else:
        print("🔄 串行模式 - 逐个处理页面")

    # 使用并行或串行模式
    if use_parallel and not skip_verification:
        # For incremental scrape, use manual parallel processing
        results = []
        for i, link in enumerate(story_links_to_scrape, 1):
            url = link['url'] if isinstance(link, dict) else link
            print(f"\r⏳ 进度: {i}/{len(story_links_to_scrape)} - {url[:80]}...", end='', flush=True)
            
            result = await scraper.scrape_single_story(url)
            results.append(result)
            
            await asyncio.sleep(scraper.delay_range[0])
        print("\n")
    elif use_parallel:
        results = await scraper.scrape_all_stories_parallel(url, max_stories)
    else:
        # 串行模式（原有逻辑）
        results = []
        for i, link in enumerate(story_links_to_scrape, 1):
            # Handle both dict (with categories) and string (without categories)
            url = link['url'] if isinstance(link, dict) else link
            print(f"\r⏳ 进度: {i}/{len(story_links_to_scrape)} - {url[:80]}...", end='', flush=True)

            result = await scraper.scrape_single_story(url)
            results.append(result)

            # 添加延迟
            await asyncio.sleep(scraper.delay_range[0])
        print("\n")

    # 显示摘要
    if not use_parallel:
        scraper.print_summary(results)

    print(f"📁 输出目录: {output_dir}/剧情/")
    print("\n")


async def scrape_all(max_pages: Optional[int], output_dir: str, max_concurrent: int = 5, no_js_render: bool = False, skip_verification: bool = False):
    """爬取全部内容（干员 + 剧情）"""
    print("\n" + "="*60)
    print("📋 阶段 1/2: 爬取干员信息")
    print("="*60 + "\n")

    await scrape_characters(CHARACTER_LIST_URL, max_pages, output_dir, no_js_render, skip_verification)

    print("\n" + "="*60)
    print("📋 阶段 2/2: 爬取剧情内容")
    print("="*60 + "\n")

    await scrape_stories(STORY_LIST_URL, max_pages, output_dir, max_concurrent, skip_verification)

    print("\n" + "="*60)
    print("🎉 全部爬取完成!")
    print("="*60)
    print(f"📁 输出目录: {output_dir}/")
    print("  - 干员/ (干员信息)")
    print("  - 剧情/ (剧情内容)")
    print("="*60 + "\n")


def parse_arguments():
    """解析命令行参数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PRTS Wiki 爬虫 - 支持干员和剧情内容爬取",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 交互模式（推荐）
  python scrape_prts.py

  # 爬取干员（从指定URL）
  python scrape_prts.py --type characters "https://prts.wiki/w/干员一览"

  # 爬取剧情（从指定URL）
  python scrape_prts.py --type stories "https://prts.wiki/w/剧情一览"

  # 爬取全部内容
  python scrape_prts.py --type all

  # 限制数量
  python scrape_prts.py --type characters --max 100

  # 自定义输出目录
  python scrape_prts.py --type stories --output ./my_docs

  # 禁用JavaScript渲染（更快但可能遗漏内容）
  python scrape_prts.py --type characters --no-js-render
        """
    )

    # URL参数（可选，不提供时使用交互模式）
    parser.add_argument(
        "url",
        nargs='?',
        help="URL to scrape (optional, will use default URLs if not provided)"
    )

    # 内容类型参数
    parser.add_argument(
        "--type", "-t",
        type=str,
        choices=["characters", "stories", "all", "character", "story"],
        help="Content type: characters (干员), stories (剧情), all (全部)"
    )

    # 最大数量参数
    parser.add_argument(
        "--max",
        type=int,
        help="Maximum number of items to scrape"
    )

    # 输出目录
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="docs/prts",
        help="Output directory (default: docs/prts)"
    )

    # JavaScript渲染选项
    parser.add_argument(
        "--no-js-render",
        action="store_true",
        help="Disable JavaScript rendering (faster but may miss dynamic content)"
    )

    # 并发控制参数
    parser.add_argument(
        "--max-concurrent", "-c",
        type=int,
        default=5,
        help="最大并发数 (default: 5, 建议: 5-8)"
    )

    parser.add_argument(
        "--serial",
        action="store_true",
        help="使用串行模式（禁用并发抓取）"
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        default=True,
        help="使用并发抓取（默认启用）"
    )

    # 交互模式
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Force interactive mode"
    )

    # 详细输出
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    # 验证选项
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip verification and scrape all content (force full scrape)"
    )

    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify without scraping"
    )

    args = parser.parse_args()

    return args


async def main():
    """主CLI函数"""
    # 显示横幅
    display_banner()

    # 解析参数
    args = parse_arguments()

    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('scraping.log', encoding='utf-8')
        ]
    )

    logger = logging.getLogger(__name__)

    try:
        # 确定模式：交互模式或命令行模式
        interactive_mode = args.interactive or (not args.type and not args.url)

        if interactive_mode:
            # 交互模式
            content_type, url, max_count, output_dir, max_concurrent = interactive_selection()
        else:
            # 命令行模式
            content_type = args.type
            max_count = args.max
            output_dir = args.output

            # 获取并发数
            if args.serial:
                max_concurrent = 1  # 串行模式
            else:
                max_concurrent = args.max_concurrent

            # 根据类型确定URL
            if content_type in ['characters', 'character']:
                if args.url:
                    url = args.url
                else:
                    url = CHARACTER_LIST_URL
            elif content_type in ['stories', 'story']:
                if args.url:
                    url = args.url
                else:
                    url = STORY_LIST_URL
            else:  # all
                url = None

        # 记录配置
        logger.info("Starting PRTS Wiki scraping")
        logger.info(f"Content type: {content_type}")
        logger.info(f"Output directory: {output_dir}")
        logger.info(f"Max count: {max_count or 'unlimited'}")
        logger.info(f"Max concurrent: {max_concurrent}")
        logger.info(f"JavaScript rendering: {'disabled' if args.no_js_render else 'enabled'}")
        logger.info(f"Verification: {'skipped' if args.skip_verification else 'enabled'}")

        # Handle verify-only mode
        if args.verify_only:
            print("\n" + "="*60)
            print("🔍 验证模式 (不执行爬取)")
            print("="*60 + "\n")
            
            verifier = PRTSVerifier(output_dir=output_dir)
            
            if content_type in ['characters', 'character', 'all']:
                print("[PRTS]$ 验证干员内容...")
                report = await verifier.verify_characters(verbose=args.verbose)
                verifier.display_prts_report(report)
            
            if content_type in ['stories', 'story', 'all']:
                print("\n[PRTS]$ 验证剧情内容...")
                report = await verifier.verify_stories(verbose=args.verbose)
                verifier.display_prts_report(report)
            
            return 0

        # 执行爬取
        if content_type == 'all':
            # 全部内容
            await scrape_all(max_count, output_dir, max_concurrent, args.no_js_render, args.skip_verification)
        elif content_type in ['characters', 'character']:
            # 干员信息
            await scrape_characters(url, max_count, output_dir, args.no_js_render, args.skip_verification)
        elif content_type in ['stories', 'story']:
            # 剧情内容
            await scrape_stories(url, max_count, output_dir, max_concurrent, args.skip_verification)
        else:
            print("❌ 无效的内容类型")
            return 1

        print("✅ 爬取完成!")
        print(f"\n📁 查看结果: {output_dir}/")
        return 0

    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        print("\n\n👋 爬取已取消")
        return 1

    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        print(f"\n❌ 错误: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
