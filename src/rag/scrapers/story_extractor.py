"""
剧情内容提取器
"""

import asyncio
import re
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page

from .story_constants import (
    STORY_SELECTORS,
    NARRATION_KEYWORDS,
    CHARACTER_SUFFIXES,
    CHAPTER_PATTERNS
)


class StoryContentExtractor:
    """剧情内容提取器"""

    def __init__(self):
        self.selectors = STORY_SELECTORS
        self.narration_keywords = NARRATION_KEYWORDS
        self.character_suffixes = CHARACTER_SUFFIXES

    async def extract_story_content(self, page: Page, url: str) -> Dict[str, Any]:
        """
        从页面提取剧情内容

        Args:
            page: Playwright页面对象
            url: 页面URL

        Returns:
            Dict[str, Any]: 提取的剧情内容
        """
        # 1. 点击播放按钮显示剧情
        await self._click_playback_button(page)

        # 2. 等待剧情内容加载
        await self._wait_for_story_content(page)

        # 3. 获取页面HTML
        html_content = await page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        # 4. 提取剧情数据
        story_data = {
            'url': url,
            'title': await self._extract_title(page),
            'chapters': self._extract_chapters(soup),
            'dialogues': await self._extract_dialogues(page),
            'narrations': self._extract_narrations(soup),
            'characters': self._extract_character_names(soup),
            'metadata': self._extract_metadata(soup, url)
        }

        # 5. 组织剧情内容
        story_data['organized_content'] = self._organize_story_content(story_data)

        return story_data

    async def _click_playback_button(self, page: Page) -> None:
        """点击播放按钮显示剧情"""
        try:
            # 等待按钮出现
            await page.wait_for_selector(
                self.selectors['playback_button'],
                timeout=10000
            )

            # 点击按钮
            await page.click(self.selectors['playback_button'])

            # 等待点击后的响应
            await asyncio.sleep(1)

        except Exception as e:
            # 如果按钮不存在或点击失败，记录日志但不中断
            print(f"Warning: Could not click playback button: {e}")

    async def _wait_for_story_content(self, page: Page) -> None:
        """等待剧情内容加载"""
        try:
            # 等待li元素出现
            await page.wait_for_selector(
                self.selectors['dialogue_list'],
                timeout=10000
            )

            # 额外等待确保内容完全加载
            await asyncio.sleep(2)

        except Exception as e:
            print(f"Warning: Story content may not have loaded: {e}")

    async def _extract_title(self, page: Page) -> str:
        """提取页面标题"""
        try:
            title = await page.title()
            return title.strip()
        except:
            return "未知剧情"

    def _extract_chapters(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取章节信息"""
        chapters = []

        # 查找所有标题
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            text = heading.get_text(strip=True)

            # 检查是否为章节标题
            if self._is_chapter_heading(text):
                chapter_data = {
                    'level': int(heading.name[1]),
                    'title': text,
                    'id': heading.get('id', ''),
                    'content_start': self._find_heading_content_start(heading)
                }
                chapters.append(chapter_data)

        return chapters

    def _is_chapter_heading(self, text: str) -> bool:
        """判断是否为章节标题"""
        # 检查是否匹配章节模式
        for pattern in CHAPTER_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True

        # 手动检查常见章节模式
        if re.match(r'^第[一二三四五六七八九十\d]+', text):
            return True
        if re.match(r'^\d+', text):
            return True
        if any(keyword in text for keyword in ['章', '话', '幕', '节']):
            return True

        return False

    def _find_heading_content_start(self, heading: Tag) -> int:
        """找到标题后内容的开始位置"""
        # 这里可以根据需要实现更复杂的内容定位逻辑
        return 0

    async def _extract_dialogues(self, page: Page) -> List[Dict[str, Any]]:
        """提取对话内容"""
        dialogues = []

        try:
            # 获取所有li元素
            li_elements = await page.query_selector_all(self.selectors['dialogue_list'])

            for i, li in enumerate(li_elements):
                # 检查是否有em标签（说话人）
                em_element = await li.query_selector(self.selectors['speaker_tag'])
                span_element = await li.query_selector(self.selectors['content_tag'])

                if em_element and span_element:
                    # 有说话人的对话
                    speaker = await em_element.inner_text()
                    content = await span_element.inner_text()

                    # 清理文本
                    speaker = self._clean_speaker_name(speaker)
                    content = self._clean_dialogue_content(content)

                    # 验证对话有效性
                    if self._is_valid_dialogue(speaker, content):
                        dialogue_data = {
                            'index': i,
                            'type': 'dialogue',
                            'speaker': speaker,
                            'content': content,
                            'speaker_em_tag': True
                        }
                        dialogues.append(dialogue_data)

                elif span_element:
                    # 可能为旁白（无em标签）
                    content = await span_element.inner_text()
                    content = self._clean_dialogue_content(content)

                    if self._is_valid_narration(content):
                        dialogue_data = {
                            'index': i,
                            'type': 'narration',
                            'content': content,
                            'speaker_em_tag': False
                        }
                        dialogues.append(dialogue_data)

        except Exception as e:
            print(f"Error extracting dialogues: {e}")

        return dialogues

    def _extract_narrations(self, soup: BeautifulSoup) -> List[Dict[str, Any]]:
        """提取旁白内容"""
        narrations = []

        li_elements = soup.find_all('li')
        for i, li in enumerate(li_elements):
            # 检查是否只有span（旁白）
            em_tag = li.find('em')
            span_tag = li.find('span')

            if span_tag and not em_tag:
                content = span_tag.get_text(strip=True)
                content = self._clean_dialogue_content(content)

                if self._is_valid_narration(content):
                    narration_data = {
                        'index': i,
                        'type': 'narration',
                        'content': content
                    }
                    narrations.append(narration_data)

        return narrations

    def _extract_character_names(self, soup: BeautifulSoup) -> List[str]:
        """提取角色名称列表"""
        characters = set()

        # 从em标签提取角色名
        em_tags = soup.find_all('em')
        for em in em_tags:
            speaker = em.get_text(strip=True)
            speaker = self._clean_speaker_name(speaker)

            if self._is_valid_character_name(speaker):
                characters.add(speaker)

        return list(characters)

    def _extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """提取页面元数据"""
        metadata = {
            'url': url,
            'extracted_at': asyncio.get_event_loop().time(),
            'total_dialogues': 0,
            'total_narrations': 0,
            'character_count': 0,
            'chapter_count': 0
        }

        # 计算统计信息
        metadata['total_dialogues'] = len(soup.find_all('em'))
        metadata['total_narrations'] = len([li for li in soup.find_all('li')
                                          if li.find('span') and not li.find('em')])
        metadata['character_count'] = len(self._extract_character_names(soup))
        metadata['chapter_count'] = len(self._extract_chapters(soup))

        return metadata

    def _organize_story_content(self, story_data: Dict[str, Any]) -> str:
        """将结构化数据组织成可读文本"""
        lines = []

        # 添加标题
        title = story_data.get('title', '未知剧情')
        lines.append(f"# {title}")
        lines.append("")

        # 添加章节（如果有）
        if story_data.get('chapters'):
            lines.append("## 章节信息")
            for chapter in story_data['chapters']:
                level = chapter['level']
                title = chapter['title']
                lines.append(f"{'#' * min(level + 2, 6)} {title}")
            lines.append("")

        # 添加对话和旁白
        lines.append("## 剧情内容")
        lines.append("")

        for item in story_data['dialogues']:
            if item['type'] == 'dialogue':
                # 对话
                speaker = item['speaker']
                content = item['content']
                lines.append(f"**{speaker}**: {content}")
            else:
                # 旁白
                content = item['content']
                lines.append(f"*{content}*")
            lines.append("")  # 空行分隔

        # 添加角色列表
        if story_data.get('characters'):
            lines.append("## 登场角色")
            for character in sorted(story_data['characters']):
                lines.append(f"- {character}")
            lines.append("")

        # 添加统计信息
        metadata = story_data.get('metadata', {})
        lines.append("## 统计信息")
        lines.append(f"- 对话数量: {metadata.get('total_dialogues', 0)}")
        lines.append(f"- 旁白数量: {metadata.get('total_narrations', 0)}")
        lines.append(f"- 登场角色: {metadata.get('character_count', 0)}")

        return '\n'.join(lines)

    def _clean_speaker_name(self, speaker: str) -> str:
        """清理说话人名称"""
        # 移除多余的符号和空格
        speaker = re.sub(r'[：:]\s*$', '', speaker)  # 移除末尾冒号
        speaker = speaker.strip()

        # 过滤角色名后缀
        for suffix in self.character_suffixes:
            if speaker.endswith(suffix):
                speaker = speaker[:-len(suffix)].strip()

        return speaker

    def _clean_dialogue_content(self, content: str) -> str:
        """清理对话内容"""
        # 移除多余的空白和换行
        content = re.sub(r'\s+', ' ', content)
        content = content.strip()

        return content

    def _is_valid_dialogue(self, speaker: str, content: str) -> bool:
        """验证对话有效性"""
        # 检查说话人是否有效
        if not self._is_valid_character_name(speaker):
            return False

        # 检查对话内容是否有效
        if len(content) < 2:  # 太短
            return False

        # 过滤系统消息
        system_keywords = ['系统', '提示', '旁白', '叙述']
        if any(keyword in speaker for keyword in system_keywords):
            return True  # 系统消息也可能是有效的

        return True

    def _is_valid_narration(self, content: str) -> bool:
        """验证旁白有效性"""
        if len(content) < 10:  # 太短的旁白
            return False

        # 检查是否包含旁白关键词
        if any(keyword in content for keyword in self.narration_keywords):
            return True

        return True

    def _is_valid_character_name(self, name: str) -> bool:
        """验证角色名有效性"""
        # 长度检查
        if len(name) < 2 or len(name) > 10:
            return False

        # 不包含特殊字符
        if re.search(r'[：:。，,\.\?\!]', name):
            return False

        # 不为空
        if not name.strip():
            return False

        # 过滤常见非角色名
        common_words = ['旁白', '叙述', '系统', '提示', '医疗干员', '术师干员']
        if name in common_words:
            return True  # 特殊标记也可能是有效的

        return True
