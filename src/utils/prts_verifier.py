"""
PRTS content verification tool.

Compares online PRTS Wiki content with locally scraped files
to detect missing or outdated content.
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import unquote, urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class PRTSVerifier:
    """Verifies completeness of locally scraped PRTS Wiki content."""

    # System pages to exclude (not actual characters/stories)
    EXCLUDED_KEYWORDS = [
        "PRTS", "公招计算", "干员一览", "剧情一览", "异常效果",
         "专属干员", "如何帮助",
        # System/navigation pages
        "首页", "争锋频道", "剧情角色一览", "采购中心", "敌人一览",
        "干员模组一览", "制作组通讯", "角色真名", "时装回廊", "卡池一览",
        "游戏数据基础", "关卡一览", "画师一览", "邮件记录", "矢量突破",
        "分支一览", "试验玩法", "干员密录一览", "作战机制", "干员专精",
        "配音一览", "干员编号", "档案信息", "任务列表", "基建", "危机合约",
        "集成战略", "新人入门", "词汇一览", "首页场景", "名片头像",
        # More system pages
        "光荣之路", "促融共竞", "音乐鉴赏", "干员预告", "后勤技能一览",
        "家具一览", "衍生作品", "活动一览", "界园志异", "游戏内容前瞻",
        "剧情资源概览", "个人名片", "复仇记", "生息演算", "班戟号",
        "贴士一览", "引航者试炼", "模拟器", "情报处理室", "界面主题",
        "保全派驻", "联锁竞赛", "多维合作", "泰拉大典", "寻访模拟",
        "道具一览"
    ]

    def __init__(self, output_dir: str = "docs/prts"):
        """
        Initialize verifier.

        Args:
            output_dir: Base directory for scraped content
        """
        self.output_dir = Path(output_dir)
        self.logger = logging.getLogger(self.__class__.__name__)

    async def verify_characters(self, verbose: bool = False) -> Dict:
        """
        Verify character content completeness.

        Args:
            verbose: Show detailed logs

        Returns:
            Dict containing verification results:
                - online_count: Number of characters online
                - local_count: Number of local files
                - matched_count: Number of matched characters
                - missing_items: List of missing character dicts (name, url)
                - extra_files: List of local files not in online list
        """
        self.logger.info("Starting character verification...")

        # Extract online character list
        online_chars = await self._extract_online_characters()
        self.logger.info(f"Found {len(online_chars)} characters online")

        # Scan local files
        local_chars = self._scan_local_characters()
        self.logger.info(f"Found {len(local_chars)} local character files")

        # Compare and generate report
        report = self._compare_lists(
            online_chars,
            local_chars,
            content_type="character"
        )

        if verbose:
            self._log_detailed_report(report)

        return report

    async def verify_stories(self, verbose: bool = False) -> Dict:
        """
        Verify story content completeness.

        Args:
            verbose: Show detailed logs

        Returns:
            Dict containing verification results
        """
        self.logger.info("Starting story verification...")

        # Extract online story list
        online_stories = await self._extract_online_stories()
        self.logger.info(f"Found {len(online_stories)} stories online")

        # Scan local files
        local_stories = self._scan_local_stories()
        self.logger.info(f"Found {len(local_stories)} local story files")

        # Compare and generate report
        report = self._compare_lists(
            online_stories,
            local_stories,
            content_type="story"
        )

        if verbose:
            self._log_detailed_report(report)

        return report

    async def _extract_online_characters(self) -> List[Dict]:
        """
        Extract character list from PRTS Wiki overview page.
        Uses a simpler approach without heavy JS rendering for better reliability.

        Returns:
            List of dicts with 'name' and 'url' keys
        """
        url = "https://prts.wiki/w/干员一览"
        
        try:
            # Use the existing scraper's method but with no-js-render mode for reliability
            from ..rag.scrapers.character_scraper import CharacterScraper
            
            self.logger.info(f"Extracting character links from {url}")
            
            # Create a scraper instance with JS rendering enabled for dynamic content
            scraper = CharacterScraper(
                output_dir=str(self.output_dir / "干员"),
                use_js_renderer=True  # Use JS rendering for dynamic content
            )
            
            # Use the scraper's method to extract all character links
            character_links = await scraper._extract_all_character_links_with_pagination(url)
            
            self.logger.info(f"Found {len(character_links)} character links")
            
            # Convert to our format
            characters = []
            excluded_count = 0
            for link in character_links:
                char_name = self._extract_name_from_url(link)
                
                # Skip special Wiki namespace pages (like "分类:", "Special:", etc.)
                if ':' in char_name and any(prefix in char_name for prefix in ['分类', 'Special', 'PRTS', '模板', 'Template']):
                    excluded_count += 1
                    self.logger.debug(f"Filtered out wiki namespace page: {char_name}")
                    continue
                
                # Filter out system pages (but keep actual character names)
                if self._is_excluded_page(char_name):
                    excluded_count += 1
                    self.logger.debug(f"Filtered out system page: {char_name}")
                    continue
                
                characters.append({
                    'name': char_name,
                    'url': link
                })
            
            self.logger.info(f"Filtered out {excluded_count} system/wiki pages")
            self.logger.info(f"Valid characters: {len(characters)}")
            return characters
            
        except Exception as e:
            self.logger.error(f"Failed to extract online characters: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    async def _extract_online_stories(self) -> List[Dict]:
        """
        Extract story list from PRTS Wiki overview page.

        Returns:
            List of dicts with 'name' and 'url' keys
        """
        from playwright.async_api import async_playwright

        url = "https://prts.wiki/w/剧情一览"
        stories = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                self.logger.info(f"Loading {url}...")
                await page.goto(url, wait_until='domcontentloaded', timeout=90000)

                # Wait for content to render
                try:
                    await page.wait_for_selector('.mw-parser-output', timeout=15000)
                    await asyncio.sleep(3)
                except Exception as e:
                    self.logger.warning(f"Wait for selector warning: {e}")

                content = await page.content()
                await browser.close()

                # Parse HTML
                soup = BeautifulSoup(content, 'html.parser')

                # Extract story links from tables (剧情一览 uses table structure)
                tables = soup.find_all('table')
                self.logger.info(f"Found {len(tables)} tables")

                for table in tables:
                    # Find all links in table
                    links = table.find_all('a', href=True)
                    
                    for link in links:
                        href = link.get('href')
                        if not href or not href.startswith('/w/'):
                            continue

                        # Skip special pages
                        if any(skip in href for skip in ['特殊:', 'Special:', '模板:', 'Template:']):
                            continue

                        full_url = f"https://prts.wiki{href}"
                        story_name = self._extract_name_from_url(full_url)

                        # Filter out system pages
                        if self._is_excluded_page(story_name):
                            continue

                        # Skip very short names (likely navigation links)
                        if len(story_name) < 2:
                            continue

                        stories.append({
                            'name': story_name,
                            'url': full_url
                        })

                # Deduplicate by name
                seen_names = set()
                unique_stories = []
                for story in stories:
                    if story['name'] not in seen_names:
                        seen_names.add(story['name'])
                        unique_stories.append(story)

                self.logger.info(f"Extracted {len(unique_stories)} unique stories")
                return unique_stories

        except Exception as e:
            self.logger.error(f"Failed to extract online stories: {e}")
            return []

    def _scan_local_characters(self) -> List[Dict]:
        """
        Scan local character files.

        Returns:
            List of dicts with 'name' and 'path' keys
        """
        char_dir = self.output_dir / "干员"
        if not char_dir.exists():
            self.logger.warning(f"Character directory not found: {char_dir}")
            return []

        characters = []
        for file_path in char_dir.glob("*.md"):
            # Extract name from filename
            char_name = file_path.stem  # Remove .md extension

            # Filter out system pages
            if self._is_excluded_page(char_name):
                continue

            characters.append({
                'name': char_name,
                'path': str(file_path)
            })

        return characters

    def _scan_local_stories(self) -> List[Dict]:
        """
        Scan local story files (recursively in subdirectories).

        Returns:
            List of dicts with 'name' and 'path' keys
        """
        stories = []
        
        # Story files are organized in subdirectories
        # e.g., docs/prts/主线剧情一览/黑暗时代·上/xxx.md
        #       docs/prts/活动剧情一览/巴别塔/xxx.md
        #       docs/prts/其他/xxx.md
        
        story_dirs = [
            self.output_dir / "主线剧情一览",
            self.output_dir / "活动剧情一览", 
            self.output_dir / "其他"
        ]

        for story_dir in story_dirs:
            if not story_dir.exists():
                self.logger.warning(f"Story directory not found: {story_dir}")
                continue

            # Recursively find all .md files
            for file_path in story_dir.glob("**/*.md"):
                # Extract name from filename
                story_name = file_path.stem

                # Filter out system pages
                if self._is_excluded_page(story_name):
                    continue

                stories.append({
                    'name': story_name,
                    'path': str(file_path),
                    'category': file_path.parent.name  # Store parent directory name
                })

        self.logger.info(f"Found {len(stories)} local story files")
        return stories

    def _compare_lists(
        self,
        online_items: List[Dict],
        local_items: List[Dict],
        content_type: str
    ) -> Dict:
        """
        Compare online and local item lists.

        Args:
            online_items: List of online items
            local_items: List of local items
            content_type: Type of content (character/story)

        Returns:
            Comparison report dict
        """
        # Normalize names for comparison
        online_names = {self._normalize_name(item['name']): item for item in online_items}
        local_names = {self._normalize_name(item['name']): item for item in local_items}

        # Find missing items (online but not local)
        missing_normalized = set(online_names.keys()) - set(local_names.keys())
        missing_items = [online_names[name] for name in missing_normalized]

        # Find extra items (local but not online)
        extra_normalized = set(local_names.keys()) - set(online_names.keys())
        extra_items = [local_names[name] for name in extra_normalized]

        # Calculate matched count
        matched_count = len(set(online_names.keys()) & set(local_names.keys()))

        return {
            'content_type': content_type,
            'online_count': len(online_items),
            'local_count': len(local_items),
            'matched_count': matched_count,
            'missing_items': missing_items,
            'extra_files': extra_items
        }

    def _normalize_name(self, name: str) -> str:
        """
        Normalize name for comparison.

        Args:
            name: Original name

        Returns:
            Normalized name
        """
        # Remove file extension
        name = name.replace('.md', '')

        # URL decode
        name = unquote(name)

        # Remove common variations
        name = name.replace(' ', '').replace('-', '').replace('_', '')

        # Lowercase for case-insensitive comparison
        name = name.lower()

        return name

    def _extract_name_from_url(self, url: str) -> str:
        """
        Extract name from PRTS Wiki URL.

        Args:
            url: PRTS Wiki URL

        Returns:
            Extracted name
        """
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path

        # Extract from path (e.g., /w/凯尔希 -> 凯尔希)
        if path.startswith('/w/'):
            name = path[3:]  # Remove /w/
        else:
            name = path

        # Remove trailing slashes
        name = name.rstrip('/')

        # URL decode
        name = unquote(name)

        return name

    def _is_excluded_page(self, name: str) -> bool:
        """
        Check if page should be excluded (system pages, etc.).

        Args:
            name: Page name

        Returns:
            True if should be excluded
        """
        for keyword in self.EXCLUDED_KEYWORDS:
            if keyword in name:
                return True
        return False

    def _is_potential_character_link(self, url: str) -> bool:
        """
        Check if URL looks like a character page.

        Args:
            url: URL to check

        Returns:
            True if likely a character page
        """
        # Basic heuristic: character pages are usually short names
        name = self._extract_name_from_url(url)

        # Skip very long names (likely system pages)
        if len(name) > 30:
            return False

        # Skip pages with special characters that indicate system pages
        if any(char in name for char in [':', '/', '?', '&']):
            return False

        return True

    def _log_detailed_report(self, report: Dict):
        """Log detailed verification report."""
        self.logger.info("=" * 60)
        self.logger.info(f"Verification Report - {report['content_type']}")
        self.logger.info("=" * 60)
        self.logger.info(f"Online items: {report['online_count']}")
        self.logger.info(f"Local items: {report['local_count']}")
        self.logger.info(f"Matched: {report['matched_count']}")
        self.logger.info(f"Missing: {len(report['missing_items'])}")
        self.logger.info(f"Extra files: {len(report['extra_files'])}")

        if report['missing_items']:
            self.logger.info("\nMissing items:")
            for item in report['missing_items'][:10]:  # Show first 10
                self.logger.info(f"  - {item['name']}: {item['url']}")
            if len(report['missing_items']) > 10:
                self.logger.info(f"  ... and {len(report['missing_items']) - 10} more")

        if report['extra_files']:
            self.logger.info("\nExtra local files:")
            for item in report['extra_files'][:10]:
                self.logger.info(f"  - {item['name']}")
            if len(report['extra_files']) > 10:
                self.logger.info(f"  ... and {len(report['extra_files']) - 10} more")

    def display_prts_report(self, report: Dict):
        """
        Display verification report in PRTS terminal style.

        Args:
            report: Verification report dict
        """
        content_type_cn = "干员" if report['content_type'] == "character" else "剧情"

        print("\n" + "=" * 60)
        print(f"[PRTS]$ 正在验证{content_type_cn}内容完整性...")
        print(f"[INFO] 连接 PRTS Wiki... 完成")
        print(f"[INFO] 扫描本地目录... 完成")
        print()
        print("==== 验证结果 ====")
        print(f"在线{content_type_cn}总数: {report['online_count']}")
        print(f"本地{content_type_cn}总数: {report['local_count']}")
        print(f"匹配{content_type_cn}数: {report['matched_count']}")
        print()

        if report['missing_items']:
            print(f"[WARN] 发现 {len(report['missing_items'])} 个未爬取的{content_type_cn}:")
            for i, item in enumerate(report['missing_items'][:20], 1):
                print(f"  {i}. {item['name']} - {item['url']}")
            if len(report['missing_items']) > 20:
                print(f"  ... 以及另外 {len(report['missing_items']) - 20} 个")
        else:
            print(f"[INFO] 所有{content_type_cn}均已爬取")

        print()
        if report['extra_files']:
            print(f"[INFO] 发现 {len(report['extra_files'])} 个本地多余文件:")
            for item in report['extra_files'][:10]:
                print(f"  - {item['name']}")
            if len(report['extra_files']) > 10:
                print(f"  ... 以及另外 {len(report['extra_files']) - 10} 个")
            print()

        print("[STATUS] 验证完成")
        print("=" * 60)

