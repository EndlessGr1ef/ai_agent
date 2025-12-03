"""
剧情页面检测器
"""

import re
from bs4 import BeautifulSoup
from typing import Optional, List, Dict, Any
from .story_constants import (
    STORY_URL_PATTERNS,
    EXCLUDED_URL_PATTERNS,
    STORY_SELECTORS
)


class StoryPageDetector:
    """剧情页面检测器"""

    def __init__(self):
        self.story_patterns = STORY_URL_PATTERNS
        self.excluded_patterns = EXCLUDED_URL_PATTERNS

    def is_story_page(self, url: str, soup: Optional[BeautifulSoup] = None) -> bool:
        """
        检测是否为剧情页面

        Args:
            url: 页面URL
            soup: BeautifulSoup对象（可选）

        Returns:
            bool: 是否为剧情页面
        """
        # 1. URL模式检测
        if self._url_excluded(url):
            return False

        if self._url_match_story(url):
            return True

        # 2. 内容特征检测
        if soup:
            return self._content_match_story(soup)

        return False

    def _url_excluded(self, url: str) -> bool:
        """检查URL是否被排除"""
        return any(pattern in url for pattern in self.excluded_patterns)

    def _url_match_story(self, url: str) -> bool:
        """检查URL是否匹配剧情模式"""
        return any(pattern in url for pattern in self.story_patterns)

    def _content_match_story(self, soup: BeautifulSoup) -> bool:
        """检查内容是否匹配剧情特征"""
        # 检测剧情特有元素
        story_indicators = 0

        # 检查是否有剧情相关文本
        text_content = soup.get_text()
        story_keywords = ['剧情', '故事', '章节', '对话', '旁白', '叙述', '场景']
        story_indicators += sum(1 for keyword in story_keywords if keyword in text_content)

        # 检查是否有对话结构
        dialogue_indicators = self._detect_dialogue_structure(soup)
        story_indicators += dialogue_indicators

        # 检查是否有章节结构
        chapter_indicators = self._detect_chapter_structure(soup)
        story_indicators += chapter_indicators

        # 阈值判断
        return story_indicators >= 2

    def _detect_dialogue_structure(self, soup: BeautifulSoup) -> int:
        """检测对话结构"""
        indicators = 0

        # 检查em标签（说话人标签）
        em_count = len(soup.find_all('em'))
        if em_count > 0:
            indicators += 1

        # 检查对话模式（角色名+冒号）
        text = soup.get_text()
        if ':' in text:
            # 简单检查是否有对话模式
            colon_count = text.count(':')
            if colon_count > 3:  # 至少3个对话
                indicators += 1

        # 检查li标签中的对话结构
        li_elements = soup.find_all('li')
        for li in li_elements:
            if li.find('em') and li.find('span'):
                indicators += 1
                break

        return min(indicators, 2)  # 最多2分

    def _detect_chapter_structure(self, soup: BeautifulSoup) -> int:
        """检测章节结构"""
        indicators = 0

        # 检查标题层级
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4'])
        if headings:
            indicators += 1

        # 检查是否有章节模式
        text_content = soup.get_text()
        chapter_patterns = [
            r'第\d+章',
            r'第\d+话',
            r'Episode\s+\d+',
            r'Chapter\s+\d+',
            r'\d+\.'
        ]

        chapter_count = sum(1 for pattern in chapter_patterns
                           if re.search(pattern, text_content))
        if chapter_count > 0:
            indicators += 1

        return min(indicators, 2)  # 最多2分

    def detect_story_type(self, url: str, soup: Optional[BeautifulSoup] = None) -> str:
        """
        检测剧情类型

        Args:
            url: 页面URL
            soup: BeautifulSoup对象（可选）

        Returns:
            str: 剧情类型 ('mainline', 'character', 'activity', 'side', 'worldview', 'general')
        """
        url_lower = url.lower()

        # 根据URL判断类型
        if any(keyword in url_lower for keyword in ['主线', 'mainline']):
            return 'mainline'
        elif any(keyword in url_lower for keyword in ['角色', 'character', '干员']):
            return 'character'
        elif any(keyword in url_lower for keyword in ['活动', 'activity', 'event']):
            return 'activity'
        elif any(keyword in url_lower for keyword in ['side', '外传']):
            return 'side'
        elif any(keyword in url_lower for keyword in ['世界观', '设定', 'worldview']):
            return 'worldview'

        # 默认类型
        return 'general'

    def should_scrape_story(self, url: str, soup: Optional[BeautifulSoup] = None) -> bool:
        """
        判断是否应该爬取此页面作为剧情

        Args:
            url: 页面URL
            soup: BeautifulSoup对象（可选）

        Returns:
            bool: 是否应该爬取
        """
        # 检查是否为剧情页面
        if not self.is_story_page(url, soup):
            return False

        # 检查是否为剧情一览页面（包含大量链接）
        if self._is_story_list_page(url, soup):
            return False  # 剧情一览页面通常不需要直接爬取内容

        # 检查是否包含具体剧情内容
        if soup and self._has_story_content(soup):
            return True

        # 通过URL判断
        if any(keyword in url for keyword in ['剧情', '故事', '活动']):
            # 排除一览页面
            if '一览' not in url and 'list' not in url.lower():
                return True

        return False

    def _is_story_list_page(self, url: str, soup: Optional[BeautifulSoup] = None) -> bool:
        """检查是否为剧情一览页面（包含大量链接）"""
        # URL包含一览或list关键词
        if any(keyword in url for keyword in ['一览', 'list', 'index', '目录']):
            return True

        # 内容包含大量链接（>10个剧情链接）
        if soup:
            links = soup.find_all('a', href=True)
            story_links = [link for link in links
                          if any(pattern in link.get('href', '') for pattern in self.story_patterns)]
            if len(story_links) > 10:
                return True

        return False

    def _has_story_content(self, soup: BeautifulSoup) -> bool:
        """检查是否包含具体剧情内容"""
        # 检查是否有对话结构
        li_elements = soup.find_all('li')
        dialogue_count = 0

        for li in li_elements:
            # 检查是否有em+span结构（对话）
            if li.find('em') and li.find('span'):
                dialogue_count += 1
                if dialogue_count >= 3:  # 至少3个对话
                    return True

        # 检查是否有旁白
        narration_count = 0
        for li in li_elements:
            # 检查是否只有span（旁白）
            if li.find('span') and not li.find('em'):
                narration_count += 1
                if narration_count >= 3:  # 至少3段旁白
                    return True

        return False

    def extract_story_links(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """
        从剧情一览页面提取所有剧情链接（原始版本，向后兼容）

        Args:
            soup: BeautifulSoup对象
            base_url: 基础URL

        Returns:
            List[str]: 剧情页面链接列表
        """
        from urllib.parse import urljoin, urlparse

        links = []

        # 查找所有table中的链接（原始逻辑）
        tables = soup.find_all('table')
        for table in tables:
            # 在table中查找所有a标签
            anchor_tags = table.find_all('a', href=True)

            for anchor in anchor_tags:
                href = anchor.get('href')

                # 跳过无效链接
                if not href or href == '#':
                    continue

                # 跳过非PRTS Wiki链接
                if not href.startswith('/w/'):
                    continue

                full_url = urljoin(base_url, href)

                # 检查链接是否指向剧情页面
                # 对于从剧情一览页面提取的链接，使用更宽松的检查
                if self._is_potential_story_link(full_url):
                    links.append(full_url)

        # 去重并排序
        return sorted(list(set(links)))

    def extract_story_links_with_categories(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """
        从剧情一览页面提取所有剧情链接（带分类信息）

        基于实际页面结构：使用h2/h3/h4标题层级组织分类
        - h2: "主线剧情一览"、"活动剧情一览" （一级分类）
        - h3: "黑暗时代·上"、"黑暗时代·下"等 （二级分类）
        - 链接：位于h3标题下方的div/p中，用"·"分隔

        Args:
            soup: BeautifulSoup对象
            base_url: 基础URL

        Returns:
            List[Dict[str, Any]]: 剧情链接列表，每个元素包含：
                - url: 完整的剧情页面URL
                - category_path: 分类路径（元组形式）
                - title: 剧情标题（可选）
        """
        from urllib.parse import urljoin

        links_with_categories = []

        # 找到所有h2标题
        h2_titles = soup.find_all('h2')

        for h2 in h2_titles:
            h2_text = h2.get_text(strip=True)

            # 检查是否为我们要的顶级分类
            if any(keyword in h2_text for keyword in ['主线剧情一览', '活动剧情一览']):
                # 解析该h2下的所有内容
                current_path = [h2_text]  # 一级分类路径

                # 遍历h2下的所有后续兄弟元素，直到下一个h2
                self._parse_heading_section(h2, base_url, current_path, links_with_categories)

        # 去重（基于URL）
        seen_urls = set()
        unique_links = []
        for link_info in links_with_categories:
            if link_info['url'] not in seen_urls:
                seen_urls.add(link_info['url'])
                unique_links.append(link_info)

        # 按分类路径排序
        return sorted(unique_links, key=lambda x: (x['category_path'], x['url']))

    def _parse_heading_section(self, heading, base_url: str, current_path: List[str], result: List[Dict[str, Any]]):
        """
        解析标题下的内容区域

        Args:
            heading: 当前h2标题元素
            base_url: 基础URL
            current_path: 当前分类路径
            result: 结果存储列表
        """
        # 获取下一个兄弟元素
        sibling = heading.find_next_sibling()

        while sibling and sibling.name != 'h2':  # 直到下一个h2
            if sibling.name == 'h3':
                # 二级分类
                h3_text = sibling.get_text(strip=True)
                new_path = current_path + [h3_text]

                # 查找h3下的链接
                self._extract_links_from_element(sibling, base_url, new_path, result)

                # 递归解析h3下的子元素（可能有h4）
                self._parse_heading_section(sibling, base_url, new_path, result)

            elif sibling.name in ['p', 'div']:
                # 直接的段落或div，可能包含链接
                self._extract_links_from_element(sibling, base_url, current_path, result)

            sibling = sibling.find_next_sibling()

    def _extract_links_from_element(self, element, base_url: str, category_path: List[str], result: List[Dict[str, Any]]):
        """
        从元素中提取链接

        Args:
            element: 要解析的HTML元素
            base_url: 基础URL
            category_path: 分类路径
            result: 结果存储列表
        """
        from urllib.parse import urljoin

        # 查找该元素及其子元素中的所有链接
        links = element.find_all('a', href=True)

        for link in links:
            href = link.get('href')

            if not href or not href.startswith('/w/'):
                continue

            full_url = urljoin(base_url, href)

            # 检查是否为潜在的剧情链接
            if self._is_potential_story_link(full_url):
                result.append({
                    'url': full_url,
                    'category_path': tuple(category_path),
                    'title': link.get_text(strip=True)
                })

    def _is_potential_story_link(self, url: str) -> bool:
        """
        检查URL是否可能是剧情链接（宽松检查）

        Args:
            url: 页面URL

        Returns:
            bool: 是否可能是剧情链接
        """
        from urllib.parse import urlparse
        import re

        # 检查是否为PRTS Wiki页面
        if 'prts.wiki' not in url:
            return False

        # 获取URL路径部分
        parsed = urlparse(url)
        path = parsed.path

        # 排除非内容页面
        exclude_patterns = [
            '/w/剧情一览',
            '/w/干员一览',
            '/w/Category:',
            '/w/Special:',
            '/w/帮助:',
            '/w/讨论:',
            '/w/模板:',
            '/w/文件:',
            '/w/索引:',
            '/w/版本记录',
            '/w/站点公告',
            '/w/更新公告',
        ]

        for pattern in exclude_patterns:
            if pattern in path:
                return False

        # 包含这些关键词的通常是剧情页面
        story_keywords = [
            '剧情', '故事', '活动', 'ENTRY', 'BEG', 'END',
            '主线', 'Side', 'Worldview', '世界观',
            'Event', 'Episode'
        ]

        # 检查URL路径
        if any(keyword in path for keyword in story_keywords):
            return True

        # 排除明显的非剧情页面
        exclude_in_path = ['图片', '文件', 'Category', 'Special', 'Help', 'Talk']

        # 如果路径中包含常见的剧情模式，也认为是剧情链接
        # 例如: /w/W2G/BEG, /w/0-1_坍塌/END, /w/EP09/ENTRY
        # 匹配类似 /w/xxx/xxx 的模式（章节或场景模式）
        if re.match(r'/w/[^/]+/(ENTRY|BEG|END)', path):
            return True

        return False
