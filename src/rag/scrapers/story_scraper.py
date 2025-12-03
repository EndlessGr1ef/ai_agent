"""
剧情爬虫主类
"""

import asyncio
import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .base_scraper import BaseScraper
from .story_detector import StoryPageDetector
from .story_extractor import StoryContentExtractor
from .story_constants import STORAGE_DIR


class StoryScraper(BaseScraper):
    """剧情页面专用爬虫"""

    def __init__(self, output_dir: str = "docs/prts/剧情", **kwargs):
        """
        初始化剧情爬虫

        Args:
            output_dir: 输出目录
            **kwargs: 传递给BaseScraper的其他参数
        """
        super().__init__(**kwargs)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 初始化组件
        self.detector = StoryPageDetector()
        self.extractor = StoryContentExtractor()

        # 设置日志
        self.logger = logging.getLogger(self.__class__.__name__)

        # Playwright相关
        self._browser = None

        # 加载已存在的文件列表（用于去重）
        self.existing_files = self._load_existing_files()
        self.logger.info(f"Loaded {len(self.existing_files)} existing story files from {self.output_dir}")

        # 缓存：URL到分类路径的映射
        self._url_to_category_cache: Dict[str, Tuple[str, ...]] = {}

    def _load_existing_files(self) -> Dict[str, str]:
        """
        加载输出目录中已存在的文件列表，用于去重

        Returns:
            Dict[str, str]: 文件名到完整路径的映射
        """
        mapping = {}
        try:
            for file_path in self.output_dir.glob("*.md"):
                mapping[file_path.name] = str(file_path)
        except Exception as e:
            self.logger.warning(f"Failed to load existing files: {e}")
        return mapping

    async def get_browser(self):
        """
        获取或创建Playwright浏览器实例

        Returns:
            Browser: Playwright浏览器实例
        """
        if self._browser is None:
            from playwright.async_api import async_playwright
            playwright = await async_playwright().start()
            self._browser = await playwright.chromium.launch(headless=True)
        return self._browser

    async def _render_page(self, url: str) -> str:
        """
        使用Playwright渲染页面并获取HTML

        Args:
            url: 页面URL

        Returns:
            str: 页面HTML内容
        """
        browser = await self.get_browser()
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)  # 等待页面加载
            html = await page.content()
            return html
        finally:
            await page.close()

    def _parse_html(self, html: str):
        """
        解析HTML内容

        Args:
            html: HTML字符串

        Returns:
            BeautifulSoup: 解析后的BeautifulSoup对象
        """
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'html.parser')

    async def scrape_story_list(self, list_url: str, with_categories: bool = False) -> List[str]:
        """
        从剧情一览页面提取所有剧情链接

        Args:
            list_url: 剧情一览页面URL
            with_categories: 是否返回带分类信息的数据（默认False，向后兼容）

        Returns:
            List[str]: 剧情页面链接列表（当with_categories=False时）
            List[Dict]: 带分类信息的列表（当with_categories=True时）
        """
        self.logger.info(f"Extracting story links from: {list_url}")

        # 获取页面HTML
        html = await self._render_page(list_url)
        soup = self._parse_html(html)

        # 提取剧情链接（使用新的方法以支持分类）
        if with_categories:
            story_data = self.detector.extract_story_links_with_categories(soup, list_url)

            # 更新URL到分类路径的缓存
            for item in story_data:
                self._url_to_category_cache[item['url']] = item['category_path']

            self.logger.info(f"Found {len(story_data)} story pages with categories")
            return story_data  # 返回带分类信息的列表
        else:
            # 保持向后兼容性，返回纯URL列表
            story_links = self.detector.extract_story_links(soup, list_url)
            self.logger.info(f"Found {len(story_links)} story pages")
            return story_links

    async def scrape_single_story(self, url: str) -> Dict[str, Any]:
        """
        爬取单个剧情页面

        Args:
            url: 剧情页面URL

        Returns:
            Dict[str, Any]: 爬取结果
        """
        self.logger.info(f"Scraping story page: {url}")

        try:
            # 1. 渲染页面
            browser = await self.get_browser()
            page = await browser.new_page()

            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)

            # 2. 提取剧情内容
            story_data = await self.extractor.extract_story_content(page, url)

            # 3. 查找分类路径
            category_path = self._resolve_category_path(url)

            # 4. 生成文件名并检查是否已存在
            filename = self._generate_filename(story_data)

            # 检查文件是否已存在（只检查文件名，不包含路径）
            if filename in self.existing_files:
                self.logger.info(f"File already exists, skipping: {filename}")
                return {
                    'success': False,
                    'url': url,
                    'title': story_data.get('title', '未知剧情'),
                    'skipped': True,
                    'reason': 'File already exists',
                    'existing_file': self.existing_files[filename]
                }

            # 5. 保存剧情内容（使用分类路径）
            saved_file = await self._save_story_content(story_data, category_path)

            # 6. 更新已存在文件列表
            self.existing_files[filename] = saved_file

            # 7. 准备返回结果
            result = {
                'success': True,
                'url': url,
                'title': story_data.get('title', '未知剧情'),
                'dialogue_count': story_data.get('metadata', {}).get('total_dialogues', 0),
                'narration_count': story_data.get('metadata', {}).get('total_narrations', 0),
                'character_count': story_data.get('metadata', {}).get('character_count', 0),
                'saved_file': saved_file,
                'category_path': category_path,  # 添加分类路径信息
                'data': story_data
            }

            self.logger.info(f"Successfully scraped: {url}")
            self.logger.info(f"Saved to: {saved_file}")
            if category_path:
                self.logger.info(f"Category path: {category_path}")

            return result

        except Exception as e:
            error_msg = f"Failed to scrape {url}: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }

        finally:
            if 'page' in locals():
                await page.close()

    async def scrape_all_stories(self, list_url: str, max_stories: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        爬取所有剧情页面

        Args:
            list_url: 剧情一览页面URL
            max_stories: 最大爬取数量（可选）

        Returns:
            List[Dict[str, Any]]: 爬取结果列表
        """
        self.logger.info(f"Starting batch scraping from: {list_url}")

        # 1. 获取所有剧情链接
        story_links = await self.scrape_story_list(list_url)

        # 2. 限制数量（如果指定）
        if max_stories:
            story_links = story_links[:max_stories]
            self.logger.info(f"Limited to {max_stories} stories")

        # 3. 批量爬取
        results = []
        total = len(story_links)

        self.logger.info(f"Scraping {total} story pages...")

        for i, url in enumerate(story_links, 1):
            self.logger.info(f"Progress: {i}/{total} - {url}")

            # 添加延迟避免请求过快
            if i > 1:
                await asyncio.sleep(self.delay_range[0])

            # 爬取单个剧情
            result = await self.scrape_single_story(url)
            results.append(result)

            # 实时保存（避免内存溢出）
            if i % 10 == 0:
                self.logger.info(f"Completed {i}/{total} stories")

        # 4. 统计结果
        success_count = sum(1 for r in results if r.get('success'))
        skipped_count = sum(1 for r in results if r.get('skipped'))
        failed_count = total - success_count - skipped_count

        self.logger.info(f"Batch scraping completed:")
        self.logger.info(f"  Total: {total}")
        self.logger.info(f"  Success: {success_count}")
        self.logger.info(f"  Skipped (already exists): {skipped_count}")
        self.logger.info(f"  Failed: {failed_count}")
        if total > 0:
            self.logger.info(f"  Success rate: {success_count/total*100:.1f}%")

        return results

    def is_target_page(self, url: str, content: Optional[str] = None) -> bool:
        """
        判断是否为剧情目标页面

        Args:
            url: 页面URL
            content: 页面内容（可选）

        Returns:
            bool: 是否为目标页面
        """
        return self.detector.should_scrape_story(url, None)

    def extract_links(self, url: str) -> List[str]:
        """
        从剧情一览页面提取所有剧情链接

        Args:
            url: 剧情一览页面URL

        Returns:
            List[str]: 剧情页面链接列表
        """
        try:
            import asyncio
            # 检查是否已经有运行中的事件循环
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # 如果有运行中的循环，使用线程池执行
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(asyncio.run, self.scrape_story_list(url))
                        return future.result()
            except RuntimeError:
                # 没有事件循环，创建新的
                pass

            # 运行异步方法
            links = asyncio.run(self.scrape_story_list(url))
            return links
        except Exception as e:
            self.logger.error(f"Failed to extract links from {url}: {e}")
            return []

    def extract_content(self, url: str) -> Dict[str, Any]:
        """
        提取剧情内容（同步方法，用于兼容性）

        Args:
            url: 页面URL

        Returns:
            Dict[str, Any]: 提取结果
        """
        # 这里实现同步版本（如果需要）
        # 对于剧情爬虫，主要使用异步方法
        raise NotImplementedError("Use scrape_single_story for async operation")

    async def _save_story_content(self, story_data: Dict[str, Any], category_path: Tuple[str, ...] = None) -> str:
        """
        保存剧情内容到文件（支持分类目录）

        Args:
            story_data: 剧情数据
            category_path: 分类路径（元组），可选

        Returns:
            str: 保存的文件路径
        """
        # 生成文件名
        filename = self._generate_filename(story_data)

        # 根据分类路径创建目录
        if category_path:
            directory = self._create_category_directories(category_path)
        else:
            directory = self.output_dir

        file_path = directory / filename

        # 获取组织后的内容
        content = story_data.get('organized_content', '')

        # 添加文件头
        content_with_header = self._add_file_header(content, story_data)

        # 保存文件
        try:
            import aiofiles
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content_with_header)

            self.logger.info(f"Saved story to: {file_path}")
            return str(file_path)

        except Exception as e:
            self.logger.error(f"Failed to save file: {e}")
            raise

    def _generate_filename(self, story_data: Dict[str, Any]) -> str:
        """
        生成文件名

        Args:
            story_data: 剧情数据

        Returns:
            str: 文件名
        """
        import re

        # 提取标题
        title = story_data.get('title', '未知剧情')

        # 删除网站名称部分（"- PRTS - 玩家共同构筑的明日方舟中文Wiki"）
        title = re.sub(r'\s*-\s*PRTS\s*-\s*玩家共同构筑的明日方舟中文Wiki\s*$', '', title)
        title = title.strip(' -').strip()

        # 清理文件名
        title = re.sub(r'[<>:"/\\|?*]', '_', title)
        title = title.strip(' .')

        # 限制长度
        if len(title) > 80:
            title = title[:80]

        # 不添加时间戳，直接返回清理后的标题
        return f"{title}.md"

    def _add_file_header(self, content: str, story_data: Dict[str, Any]) -> str:
        """
        添加文件头部元数据

        Args:
            content: 文件内容
            story_data: 剧情数据

        Returns:
            str: 带有头部的内容
        """
        lines = ['---']

        # 基本信息
        lines.append(f"title: {story_data.get('title', '未知剧情')}")
        lines.append(f"url: {story_data.get('url', '')}")
        lines.append(f"content_type: story")
        lines.append(f"extracted_at: {story_data.get('metadata', {}).get('extracted_at', '')}")

        # 统计信息
        metadata = story_data.get('metadata', {})
        lines.append(f"dialogue_count: {metadata.get('total_dialogues', 0)}")
        lines.append(f"narration_count: {metadata.get('total_narrations', 0)}")
        lines.append(f"character_count: {metadata.get('character_count', 0)}")
        lines.append(f"chapter_count: {metadata.get('chapter_count', 0)}")

        # 角色列表
        characters = story_data.get('characters', [])
        if characters:
            lines.append(f"characters: {', '.join(characters)}")

        lines.append('---')
        lines.append('')

        return '\n'.join(lines) + content

    def get_statistics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        获取爬取统计信息

        Args:
            results: 爬取结果列表

        Returns:
            Dict[str, Any]: 统计信息
        """
        if not results:
            return {}

        success_results = [r for r in results if r.get('success')]
        skipped_results = [r for r in results if r.get('skipped')]
        failed_results = [r for r in results if not r.get('success') and not r.get('skipped')]

        # 计算总统计
        total_dialogues = sum(r.get('dialogue_count', 0) for r in success_results)
        total_narrations = sum(r.get('narration_count', 0) for r in success_results)
        total_characters = len(set(char for r in success_results
                                  for char in r.get('data', {}).get('characters', [])))

        statistics = {
            'total_pages': len(results),
            'success_count': len(success_results),
            'skipped_count': len(skipped_results),
            'failed_count': len(failed_results),
            'success_rate': len(success_results) / len(results) * 100 if results else 0,
            'total_dialogues': total_dialogues,
            'total_narrations': total_narrations,
            'unique_characters': total_characters,
            'average_dialogues_per_story': total_dialogues / len(success_results) if success_results else 0,
            'output_directory': str(self.output_dir)
        }

        return statistics

    def print_summary(self, results: List[Dict[str, Any]]) -> None:
        """
        打印爬取摘要

        Args:
            results: 爬取结果列表
        """
        stats = self.get_statistics(results)

        print("\n" + "="*60)
        print("剧情爬取摘要")
        print("="*60)
        print(f"总页面数: {stats['total_pages']}")
        print(f"成功数量: {stats['success_count']}")
        print(f"跳过数量 (已存在): {stats['skipped_count']}")
        print(f"失败数量: {stats['failed_count']}")
        print(f"总对话数: {stats['total_dialogues']}")
        print(f"总旁白数: {stats['total_narrations']}")
        print(f"独特角色数: {stats['unique_characters']}")
        print(f"平均对话数/剧情: {stats['average_dialogues_per_story']:.1f}")
        print(f"输出目录: {stats['output_directory']}")
        print("="*60)

        # 打印失败的URL
        failed_results = [r for r in results if not r.get('success') and not r.get('skipped')]
        if failed_results:
            print(f"\n失败的页面 ({len(failed_results)}):")
            for result in failed_results[:5]:  # 只显示前5个
                print(f"  - {result['url']}: {result.get('error', 'Unknown error')}")
            if len(failed_results) > 5:
                print(f"  ... and {len(failed_results) - 5} more")

    def _create_category_directories(self, category_path: Tuple[str, ...]) -> Path:
        """
        根据分类路径创建多级目录

        Args:
            category_path: 分类路径，如 ('主线剧情一览', '黑暗时代·上', '序章')

        Returns:
            Path: 创建的目录路径
        """
        import re

        # 清理路径组件
        clean_path = []
        for component in category_path:
            # 移除/替换非法字符
            clean = re.sub(r'[<>:"/\\|?*]', '_', component)
            # 限制长度避免路径过长
            clean = clean[:50]
            # 避免空字符串
            if clean and clean.strip():
                clean_path.append(clean.strip())

        if not clean_path:
            return self.output_dir

        # 创建目录
        dir_path = self.output_dir
        for folder in clean_path:
            dir_path = dir_path / folder
            dir_path.mkdir(parents=True, exist_ok=True)

        return dir_path

    def _resolve_category_path(self, url: str) -> Tuple[str, ...]:
        """
        根据URL解析分类路径

        Args:
            url: 剧情页面URL

        Returns:
            Tuple[str, ...]: 分类路径，如果没有找到则返回空元组
        """
        return self._url_to_category_cache.get(url, tuple())
