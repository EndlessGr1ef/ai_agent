"""
Character (干员) scraper for PRTS Wiki.
专门用于提取干员信息的爬虫类。
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin

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
        
        # 移除常见的Wiki后缀
        name = re.sub(r'\s*-\s*PRTS.*$', '', title)
        name = re.sub(r'\s*-\s*明日方舟.*$', '', name)
        
        # 清理非法字符
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = name.strip(' .')
        
        # 限制长度
        if len(name) > 80:
            name = name[:80]
            
        return f"{name}.md"

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
                if self.use_js_renderer:
                    await self._ensure_js_renderer()
                    page_data = await self.js_renderer.render_page(
                        link,
                        wait_for_function="() => document.readyState === 'complete'"
                    )
                    html_content = page_data['html']
                else:
                    response = self.make_request(link)
                    html_content = response.text

                soup = BeautifulSoup(html_content, 'html.parser')

                # 检查是否为干员页面
                if self._is_character_page(link, soup):
                    character_links.append(link)
                    logger.debug(f"Confirmed character page: {link}")

            except Exception as e:
                logger.warning(f"Failed to check link {link}: {e}")
                continue

        logger.info(f"Filtered {len(character_links)} character links from {len(links)} total links")
        return character_links

    async def _extract_all_character_links_with_pagination(self, start_url: str, max_pages: int = None) -> List[str]:
        """
        提取所有干员链接（带分页处理）。

        Args:
            start_url: 起始URL（通常是干员一览页面）
            max_pages: 最大页数限制（None表示不限制）

        Returns:
            List[str]: 所有干员链接列表
        """
        logger.info(f"Starting character link extraction from: {start_url}")
        all_links = []
        seen_links = set()  # 用于去重

        page_count = 0
        max_pages_limit = max_pages if max_pages else 100  # 默认最多100页

        if self.use_js_renderer:
            # 使用Playwright JavaScript渲染模式
            await self._ensure_js_renderer()
            page = None

            try:
                # 创建单个页面会话用于整个分页过程
                page = await self.js_renderer._context.new_page()
                await page.goto(start_url, wait_until='domcontentloaded')

                while page_count < max_pages_limit:
                    page_count += 1

                    # 等待Vue.js渲染
                    await page.wait_for_selector('#result .long-container', timeout=15000)
                    await page.wait_for_timeout(2000)

                    logger.info(f"Processing page {page_count}")

                    # 提取当前页的链接
                    page_links = await page.evaluate('''() => {
                        const links = [];
                        const containers = document.querySelectorAll('#result .long-container, #filter-result .long-container');
                        containers.forEach(container => {
                            const nameA = container.querySelector('.name a[href]');
                            if (nameA && nameA.href) {
                                const href = nameA.href;
                                if (href.includes('/w/') && !href.includes('Special:') &&
                                    !href.includes('Template:') && !href.includes('Category:') &&
                                    !href.includes('File:') && !href.includes('Help:')) {
                                    links.push(href);
                                }
                            }
                        });
                        return links;
                    }''')

                    # 获取当前页码和最大页码
                    page_info = await page.evaluate('''() => {
                        const selected = document.querySelector('.checkbox-container .selected');
                        const currentPage = selected ? parseInt(selected.textContent) : 1;
                        // 只选择包含纯数字的页码按钮（排除合并的职业筛选按钮）
                        const containers = Array.from(document.querySelectorAll('.checkbox-container'))
                            .filter(c => c.textContent.trim().match(/^\\d+$/));
                        return { currentPage, maxPage: containers.length };
                    }''')

                    logger.info(f"Found {len(page_links)} links on page {page_info['currentPage']}")

                    # 添加新链接（去重）
                    new_count = 0
                    for link in page_links:
                        if link not in seen_links:
                            seen_links.add(link)
                            all_links.append(link)
                            new_count += 1

                    logger.info(f"Added {new_count} new character links (total: {len(all_links)})")

                    # 如果达到最大页数限制
                    if page_count >= max_pages_limit:
                        logger.info(f"Reached max pages limit: {max_pages_limit}")
                        break

                    # 如果还有下一页，点击它
                    if page_info['currentPage'] < page_info['maxPage']:
                        next_page_num = page_info['currentPage'] + 1
                        await page.evaluate(f'''() => {{
                            const containers = document.querySelectorAll('.checkbox-container');
                            for (let container of containers) {{
                                const text = container.textContent.trim();
                                if (text === "{next_page_num}") {{
                                    container.click();
                                    break;
                                }}
                            }}
                        }}''')
                        # 等待Vue.js渲染
                        await page.wait_for_timeout(3000)
                    else:
                        logger.info("No more pages found")
                        break

                    # 添加延迟避免请求过快
                    await asyncio.sleep(self.delay_range[0])

            except Exception as e:
                logger.error(f"Error during pagination: {e}")
            finally:
                if page:
                    await page.close()

        else:
            # 传统HTTP请求模式
            current_url = start_url

            while current_url and page_count < max_pages_limit:
                page_count += 1
                logger.info(f"Processing page {page_count}: {current_url}")

                try:
                    response = self.make_request(current_url)
                    soup = BeautifulSoup(response.text, 'html.parser')
                    page_links = self._extract_character_links_from_list_page(soup, current_url)

                    logger.info(f"Found {len(page_links)} links on page {page_count}")

                    # 添加新链接（去重）
                    new_count = 0
                    for link in page_links:
                        if link not in seen_links:
                            seen_links.add(link)
                            all_links.append(link)
                            new_count += 1

                    logger.info(f"Added {new_count} new character links (total: {len(all_links)})")

                    # 获取下一页 URL
                    next_url = self._extract_next_page_url(soup, current_url)
                    if next_url and next_url != current_url:
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

    async def _extract_links_via_js(self, url: str) -> List[str]:
        """使用 JavaScript 从渲染后的页面提取干员链接"""
        try:
            await self._ensure_js_renderer()

            # 渲染页面
            page_data = await self.js_renderer.render_page(url)
            page = None

            try:
                # 创建一个新页面来执行 JavaScript 查询
                page = await self.js_renderer._context.new_page()

                # 先设置内容（这不会触发 Vue 渲染）
                await page.set_content(page_data['html'], wait_until='domcontentloaded')

                # 关键：重新在当前上下文中加载原始 URL，让 Vue 渲染
                await page.goto(url, wait_until='domcontentloaded')

                # 等待 Vue 渲染完成
                try:
                    await page.wait_for_selector('#result .long-container, #filter-result .long-container', timeout=10000)
                except:
                    pass

                # 额外等待确保渲染完成
                await page.wait_for_timeout(3000)

                # 使用 JavaScript 提取链接
                links = await page.evaluate("""
                    () => {
                        const links = [];
                        // 查找 #result 或 #filter-result 中的 long-container
                        const containers = document.querySelectorAll('#result .long-container, #filter-result .long-container');
                        containers.forEach(container => {
                            const nameA = container.querySelector('.name a[href]');
                            if (nameA && nameA.href) {
                                const href = nameA.href;
                                if (href.includes('/w/') && !href.includes('Special:') &&
                                    !href.includes('Template:') && !href.includes('Category:') &&
                                    !href.includes('File:') && !href.includes('Help:')) {
                                    links.push(href);
                                }
                            }
                        });
                        return links;
                    }
                """)

                logger.debug(f"JS extracted {len(links)} operator links")
                return links
            finally:
                if page:
                    await page.close()

        except Exception as e:
            logger.warning(f"Failed to extract links via JS: {e}")
            return []

    async def _extract_next_page_via_js(self, url: str) -> Optional[str]:
        """使用 JavaScript 点击翻页按钮并返回新URL"""
        try:
            await self._ensure_js_renderer()
            page = None

            try:
                page = await self.js_renderer._context.new_page()
                await page.goto(url, wait_until='domcontentloaded')

                # 等待渲染
                await page.wait_for_selector('#result .long-container', timeout=15000)
                await page.wait_for_timeout(2000)

                # 获取当前页码
                current_info = await page.evaluate('''() => {
                    const selected = document.querySelector('.checkbox-container .selected');
                    const currentPage = selected ? parseInt(selected.textContent) : 1;
                    const containers = document.querySelectorAll('.checkbox-container');
                    const maxPage = containers.length;
                    return { currentPage, maxPage };
                }''')

                current_page = current_info.get('currentPage', 1)
                max_page = current_info.get('maxPage', 1)

                logger.info(f"Current page: {current_page}, Max page: {max_page}")

                # 如果还有下一页，点击它
                if current_page < max_page:
                    next_page_num = current_page + 1
                    # 点击下一个页码按钮
                    await page.evaluate(f'''() => {{
                        const containers = document.querySelectorAll('.checkbox-container');
                        for (let container of containers) {{
                            const text = container.textContent.trim();
                            if (text === "{next_page_num}") {{
                                container.click();
                                break;
                            }}
                        }}
                    }}''')

                    # 等待Vue.js渲染
                    await page.wait_for_timeout(3000)

                    # 返回当前URL（页面已经更新）
                    return page.url

                return None
            finally:
                if page:
                    await page.close()

        except Exception as e:
            logger.warning(f"Failed to extract next page via JS: {e}")
            return None

    def _extract_character_links_from_list_page(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        从干员列表页面直接提取干员链接（不验证，更快）。

        Args:
            soup: BeautifulSoup对象
            base_url: 基础URL

        Returns:
            List[str]: 干员链接列表
        """
        links = []

        # 打印页面结构用于调试
        all_ids = [tag.get('id') for tag in soup.find_all(id=True)]
        self.logger.debug(f"Page IDs: {all_ids[:20]}")

        # 使用 Playwright evaluate 获取渲染后的内容
        if hasattr(self, 'js_renderer') and self.js_renderer:
            try:
                # 使用 JavaScript 直接从 DOM 提取干员链接
                links = self.js_renderer.evaluate_js_function(base_url, """
                    () => {
                        const links = [];
                        // 查找 #result 或 #filter-result 中的 long-container
                        const containers = document.querySelectorAll('#result .long-container, #filter-result .long-container');
                        containers.forEach(container => {
                            const nameA = container.querySelector('.name a[href]');
                            if (nameA && nameA.href) {
                                const href = nameA.href;
                                if (href.includes('/w/') && !href.includes('Special:') &&
                                    !href.includes('Template:') && !href.includes('Category:') &&
                                    !href.includes('File:') && !href.includes('Help:')) {
                                    links.push(href);
                                }
                            }
                        });
                        return links;
                    }
                """)
                self.logger.debug(f"Extracted {len(links)} operator links from rendered DOM")
                return links
            except Exception as e:
                self.logger.warning(f"Failed to extract links via JS: {e}")

        # 备用方案：使用 BeautifulSoup 解析
        result_div = soup.select_one('#result, #filter-result')
        if result_div:
            containers = result_div.select('.long-container')
            self.logger.debug(f"Found {len(containers)} long-container elements")

            for container in containers:
                name_a = container.select_one('.name a[href]')
                if name_a:
                    href = name_a.get('href', '')
                    if href and href.startswith('/w/'):
                        if not any(skip in href for skip in ['Special:', 'Template:', 'Category:', 'File:', 'Help:']):
                            full_url = urljoin(base_url, href)
                            if full_url not in links:
                                links.append(full_url)

        self.logger.debug(f"Extracted {len(links)} operator links")
        return links

    def _is_valid_character_name(self, name: str) -> bool:
        """验证是否为有效的干员名称"""
        if not name or len(name) < 1 or len(name) > 15:
            return False

        # 排除系统页面关键词
        excluded_keywords = [
            '一览', '列表', '首页', '分类', 'Special', 'Template',
            '帮助', '编辑', '讨论', '历史', '相关', '导航',
            'PRTS', '公招', '计算', '干员', '剧情'
        ]

        for keyword in excluded_keywords:
            if keyword in name:
                return False

        # 排除包含特殊字符的链接
        if any(char in name for char in [':', '/', '?', '&', '<', '>', '[', ']']):
            return False

        return True

    def _is_valid_operator_name(self, name: str) -> bool:
        """
        验证是否为有效的干员名称（严格模式）。
        真正的干员名是中文2-4个字。
        """
        if not name:
            return False

        # 干员名必须是中文2-4个字
        if len(name) < 2 or len(name) > 4:
            return False

        # 必须全是中文字符
        for char in name:
            if not '\u4e00' <= char <= '\u9fff':
                return False

        # 排除已知非干员关键词
        excluded_keywords = [
            '一览', '列表', '首页', '分类', '帮助', '编辑',
            '讨论', '历史', '相关', '导航', '公招', '计算',
            '剧情', '活动', '攻略', '公告', '更新'
        ]

        for keyword in excluded_keywords:
            if keyword in name:
                return False

        return True

    def _extract_next_page_url(self, soup: BeautifulSoup, current_url: str) -> Optional[str]:
        """
        提取下一页的URL（支持 PRTS Wiki 的 Vue.js 动态分页）。

        Args:
            soup: BeautifulSoup对象
            current_url: 当前页面URL

        Returns:
            Optional[str]: 下一页URL，如果不存在则返回None
        """
        from urllib.parse import urljoin, parse_qs, urlparse

        # 1. 首先尝试从 URL 参数中提取当前页码
        current_page = self._extract_page_number_from_url(current_url)
        if current_page is None:
            current_page = 1

        # 2. 查找 PRTS Wiki 的 Vue.js 分页元素
        # 查找包含页码的 checkbox-container 元素
        page_containers = soup.select('.checkbox-container, [data-v-31ddfa9a], [data-v-7bc26d06]')

        # 提取所有页码
        available_pages = []
        for container in page_containers:
            text = container.get_text(strip=True)
            if text.isdigit():
                page_num = int(text)
                if page_num <= 100:  # 合理的页码限制
                    available_pages.append(page_num)

        available_pages = sorted(set(available_pages))
        self.logger.debug(f"Available pages: {available_pages}, current: {current_page}")

        # 3. 查找下一页
        next_page = None
        for page in available_pages:
            if page > current_page:
                next_page = page
                break

        if next_page:
            # 构建下一页 URL
            if '?' in current_url:
                base_url = current_url.split('?')[0]
                next_url = f"{base_url}?page={next_page}"
            else:
                next_url = f"{current_url}?page={next_page}"
            self.logger.info(f"Found next page: {next_url}")
            return next_url

        # 4. 备用方案：查找"下一页"文本链接
        next_link = soup.find('a', string=lambda text: text and ('下一页' in text or 'next' in text.lower()))
        if next_link and next_link.get('href'):
            return urljoin(current_url, next_link['href'])

        # 5. 查找带有 page 参数的链接
        next_page_links = soup.select('a[href*="?page="], a[href*="&page="]')
        for link in next_page_links:
            href = link.get('href')
            page_num = self._extract_page_number_from_url(href)
            if page_num and page_num > current_page:
                return urljoin(current_url, href)

        self.logger.debug("No next page found")
        return None

    def _extract_page_number_from_url(self, url: str) -> Optional[int]:
        """从 URL 中提取页码"""
        try:
            from urllib.parse import parse_qs, urlparse
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if 'page' in params:
                return int(params['page'][0])
        except Exception:
            pass
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
            if self.use_js_renderer:
                await self._ensure_js_renderer()
                page_data = await self.js_renderer.render_page(
                    url,
                    wait_for_function="() => document.readyState === 'complete'"
                )
                html_content = page_data['html']
            else:
                response = self.make_request(url)
                html_content = response.text

            soup = BeautifulSoup(html_content, 'html.parser')

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
