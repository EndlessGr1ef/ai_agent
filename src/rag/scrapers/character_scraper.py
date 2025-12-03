"""
Character (干员) scraper for PRTS Wiki.
专门用于提取干员信息的爬虫类。
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

from .prts_wiki_scraper import PRTSWikiScraper
from .base_scraper import ScrapingError
from ..config.scraper_constants import (
    CHARACTER_URL_PATTERNS, EXCLUDED_PATTERNS,
    MIN_CHARACTER_NAME_LENGTH
)

logger = logging.getLogger(__name__)


class CharacterScraper(PRTSWikiScraper):
    """
    Character scraper专门用于提取干员信息。

    继承自PRTSWikiScraper，获得所有通用方法，
    并添加干员专用的识别和提取逻辑。
    """

    def __init__(self, output_dir: str = None, **kwargs):
        """
        初始化干员爬虫。

        Args:
            output_dir: 输出目录
            **kwargs: 传递给父类的参数
        """
        # Extract output_dir before passing to parent
        self.output_dir = output_dir

        super().__init__(output_dir=None, **kwargs)

        # 设置输出目录
        if self.output_dir:
            from pathlib import Path
            self.output_dir = Path(self.output_dir)
            self.output_dir.mkdir(parents=True, exist_ok=True)
        else:
            from pathlib import Path
            self.output_dir = Path("docs/prts/干员")
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # 干员页面识别
        self.character_indicators = [
            '干员', '角色', 'character', 'operator',
            '技能', '天赋', '精英化', '等级',
            '生命上限', '攻击', '防御', '法抗'
        ]

        # Initialize logger after parent init
        self.logger = logging.getLogger(self.__class__.__name__)

        # 加载已存在的文件列表（用于去重）
        self.existing_files = self._load_existing_files()
        self.logger.info(f"Loaded {len(self.existing_files)} existing character files from {self.output_dir}")

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

    async def extract_single_character(self, url: str) -> Dict[str, Any]:
        """
        提取单个干员信息

        Args:
            url: 干员页面URL

        Returns:
            Dict[str, Any]: 提取结果
        """
        self.logger.info(f"Extracting character page: {url}")

        try:
            # 异步提取内容
            result = await self._extract_content_async(url)

            if not result or not result.get('content'):
                return {
                    'success': False,
                    'url': url,
                    'error': 'No content extracted'
                }

            # 生成文件名
            title = result.get('title', 'Unknown Character')
            filename = self._generate_filename(title)

            # 检查文件是否已存在
            if filename in self.existing_files:
                self.logger.info(f"File already exists, skipping: {filename}")
                return {
                    'success': False,
                    'url': url,
                    'title': title,
                    'skipped': True,
                    'reason': 'File already exists',
                    'existing_file': self.existing_files[filename]
                }

            # 保存文件
            import aiofiles
            file_path = self.output_dir / filename

            content = result.get('content', '')
            content_with_header = self._add_file_header(content, result)

            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content_with_header)

            # 更新已存在文件列表
            self.existing_files[filename] = str(file_path)

            self.logger.info(f"Successfully extracted: {url}")
            self.logger.info(f"Saved to: {file_path}")

            return {
                'success': True,
                'url': url,
                'title': title,
                'saved_file': str(file_path),
                'data': result
            }

        except Exception as e:
            error_msg = f"Failed to extract {url}: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'url': url,
                'error': str(e)
            }

    def _generate_filename(self, title: str) -> str:
        """
        生成文件名

        Args:
            title: 干员标题

        Returns:
            str: 文件名
        """
        import re
        from datetime import datetime

        # 清理标题
        title = re.sub(r'[<>:"/\\|?*]', '_', title)
        title = title.strip(' .')

        # 限制长度
        if len(title) > 80:
            title = title[:80]

        # 不添加时间戳
        return f"{title}.md"

    def _add_file_header(self, content: str, data: Dict[str, Any]) -> str:
        """
        添加文件头部元数据

        Args:
            content: 文件内容
            data: 数据

        Returns:
            str: 带有头部的内容
        """
        lines = ['---']

        lines.append(f"title: {data.get('title', 'Unknown')}")
        lines.append(f"url: {data.get('url', '')}")
        lines.append(f"content_type: character")
        lines.append(f"extracted_at: {data.get('timestamp', '')}")

        lines.append('---')
        lines.append('')

        return '\n'.join(lines) + content

    def _extract_character_name(self, title: str, url: str) -> str:
        """
        从标题或URL中提取角色名。

        Args:
            title: 页面标题
            url: 页面URL

        Returns:
            str: 提取的角色名
        """
        import re

        # 移除常见的Wiki后缀
        title = re.sub(r'\s*-\s*PRTS.*$', '', title)
        title = re.sub(r'\s*-\s*明日方舟.*$', '', title)

        # 如果标题不干净或太长，从URL中提取
        if not title or len(title) > 50:
            url_parts = url.split('/')
            if url_parts:
                name = url_parts[-1].replace('_', ' ')
                return name

        return title

    def _is_character_page(self, url: str, soup: BeautifulSoup = None) -> bool:
        """
        检查页面是否为干员页面。

        PRTS的干员URL都是URL编码的，没有明显的特征，
        因此需要通过分析页面内容来判断是否为干员页面。

        Args:
            url: 页面URL
            soup: BeautifulSoup对象（可选）

        Returns:
            bool: 是否为干员页面
        """
        # 首先排除明显的非干员页面（通过URL）
        if any(exclude in url for exclude in ['一览', 'list', 'index', 'category', 'Category:', 'Template:']):
            return False

        # 如果没有提供soup，仅通过URL判断
        if not soup:
            return False

        # 通过内容检测干员页面
        return self._detect_character_page_by_content(soup)

    def _detect_character_page_by_content(self, soup: BeautifulSoup) -> bool:
        """
        通过页面内容检测是否为干员页面。

        Args:
            soup: BeautifulSoup对象

        Returns:
            bool: 是否为干员页面
        """
        indicators = 0

        # 检查是否包含角色信息表格
        if soup.select('.charbox, .operator-card, .character-card'):
            indicators += 2

        # 检查是否包含角色属性信息
        text_content = soup.get_text().lower()

        character_stats = [
            '生命上限', '生命', '攻击', '防御', '法抗',
            'cost', '部署时间', '攻击间隔',
            '天赋', '技能', '精英化',
            '干员', '角色', 'operator', 'character'
        ]

        for stat in character_stats:
            if stat in text_content:
                indicators += 1

        # 检查是否包含技能信息
        skills_section = soup.find(['h2', 'h3', 'h4'], string=lambda text: text and '技能' in text)
        if skills_section:
            indicators += 2

        # 检查是否包含天赋信息
        talent_section = soup.find(['h2', 'h3', 'h4'], string=lambda text: text and '天赋' in text)
        if talent_section:
            indicators += 2

        # 检查是否包含特性信息
        trait_section = soup.find(['h2', 'h3', 'h4'], string=lambda text: text and '特性' in text)
        if trait_section:
            indicators += 1

        # 检查是否包含数据表格
        tables = soup.find_all('table')
        for table in tables:
            table_text = table.get_text().lower()
            # 检查表格是否包含角色属性
            if any(stat in table_text for stat in ['生命', '攻击', '防御', 'cost']):
                indicators += 1
                break

        # 如果指标达到3个或以上，认为是干员页面
        return indicators >= 3

    async def _filter_character_links(self, links: List[str]) -> List[str]:
        """
        过滤出干员链接。

        Args:
            links: 原始链接列表

        Returns:
            List[str]: 过滤后的干员链接列表
        """
        character_links = []

        for link in links:
            try:
                # 跳过明显的非干员链接
                if any(exclude in link for exclude in EXCLUDED_PATTERNS):
                    continue

                # 跳过列表页面
                if any(list_indicator in link for list_indicator in ['一览', 'list', 'index']):
                    continue

                # 获取页面内容进行判断
                await self._ensure_js_renderer()
                page_data = await self.js_renderer.render_page(
                    link,
                    wait_for_function="() => document.readyState === 'complete'"
                )

                soup = BeautifulSoup(page_data['html'], 'html.parser')

                # 检查是否为干员页面
                if self._is_character_page(link, soup):
                    character_links.append(link)
                    logger.debug(f"Confirmed character page: {link}")

            except Exception as e:
                logger.warning(f"Failed to check link {link}: {e}")
                continue

        logger.info(f"Filtered {len(character_links)} character links from {len(links)} total links")
        return character_links

    async def _extract_all_character_links_with_pagination(self, start_url: str) -> List[str]:
        """
        提取所有干员链接（带分页处理）。

        Args:
            start_url: 起始URL（通常是干员一览页面）

        Returns:
            List[str]: 所有干员链接列表
        """
        logger.info(f"Starting character link extraction from: {start_url}")
        all_links = []

        current_url = start_url
        page_count = 0
        max_pages = 100  # 设置最大页数防止无限循环

        while current_url and page_count < max_pages:
            page_count += 1
            logger.info(f"Processing page {page_count}: {current_url}")

            try:
                # 获取页面内容
                await self._ensure_js_renderer()
                page_data = await self.js_renderer.render_page(
                    current_url,
                    wait_for_function="() => document.readyState === 'complete'"
                )

                soup = BeautifulSoup(page_data['html'], 'html.parser')

                # 提取当前页面的链接
                page_links = self._extract_links_from_soup(soup, current_url)
                logger.info(f"Found {len(page_links)} links on page {page_count}")

                # 过滤干员链接
                character_links = await self._filter_character_links(page_links)
                all_links.extend(character_links)
                logger.info(f"Added {len(character_links)} character links (total: {len(all_links)})")

                # 查找下一页链接
                next_url = self._extract_next_page_url(soup, current_url)
                if next_url:
                    logger.info(f"Next page found: {next_url}")
                    current_url = next_url
                else:
                    logger.info("No more pages found")
                    break

                # 添加延迟避免请求过快
                await asyncio.sleep(self.delay_range[0])

            except Exception as e:
                logger.error(f"Error processing page {current_url}: {e}")
                break

        logger.info(f"Character link extraction completed: {len(all_links)} links found")
        return all_links

    def _extract_next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        提取下一页的URL。

        Args:
            soup: BeautifulSoup对象
            current_url: 当前页面URL

        Returns:
            Optional[str]: 下一页URL，如果不存在则返回None
        """
        from urllib.parse import urljoin

        # 查找"下一页"或类似链接
        next_link = soup.find('a', string=lambda text: text and ('下一页' in text or 'next' in text.lower()))

        if next_link and next_link.get('href'):
            return urljoin(current_url, next_link['href'])

        return None

    async def _extract_links_async(self, url: str) -> List[str]:
        """
        异步提取链接（干员专用版本）。

        Args:
            url: 要提取链接的页面URL

        Returns:
            List[str]: 链接列表
        """
        logger.info(f"Extracting character links from: {url}")

        try:
            await self._ensure_js_renderer()
            page_data = await self.js_renderer.render_page(
                url,
                wait_for_function="() => document.readyState === 'complete'"
            )

            soup = BeautifulSoup(page_data['html'], 'html.parser')

            # 提取所有链接
            all_links = self._extract_links_from_soup(soup, url)

            # 过滤出干员链接
            character_links = await self._filter_character_links(all_links)

            logger.info(f"Extracted {len(character_links)} character links from {url}")
            return character_links

        except Exception as e:
            logger.error(f"Failed to extract links from {url}: {e}")
            return []

    def is_target_page(self, url: str, content: str = None) -> bool:
        """
        判断页面是否为目标页面（干员页面）。

        Args:
            url: 页面URL
            content: 页面内容（可选）

        Returns:
            bool: 是否为目标页面
        """
        if content:
            soup = BeautifulSoup(content, 'html.parser')
            return self._is_character_page(url, soup=soup)
        return self._is_character_page(url, soup=None)
