"""PRTS Wiki scraper for character information and related content."""

import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScrapingError
from ..extractors.js_renderer import JSRenderer
from ..config.scraper_constants import (
    CSS_SELECTORS, CHARACTER_URL_PATTERNS, EXCLUDED_PATTERNS,
    MAX_PAGINATION_PAGES, MIN_CHARACTER_NAME_LENGTH, MAX_LINE_LENGTH_FOR_MERGE,
    PAGE_NAVIGATION_WAIT, SELECTOR_TIMEOUT
)

logger = logging.getLogger(__name__)


class PRTSWikiScraper(BaseScraper):
    """Scraper specifically designed for PRTS Wiki (prts.wiki)."""
    
    def __init__(self, 
                 use_js_renderer: bool = True,
                 content_selectors: Dict[str, str] = None,
                 **kwargs):
        """
        Initialize PRTS Wiki scraper.
        
        Args:
            use_js_renderer: Whether to use JavaScript rendering for dynamic content
            content_selectors: CSS selectors for different content types
            **kwargs: Additional arguments for BaseScraper
        """
        super().__init__(**kwargs)
        
        self.base_url = "https://prts.wiki"
        self.use_js_renderer = use_js_renderer
        self.js_renderer = None
        
        # Default CSS selectors for PRTS wiki content
        self.content_selectors = content_selectors or {
            'character_list': '.smw-columnlist-container, .character-list, .wikitable, .operator-list',
            'character_info': '.character-info, .infobox, .character-detail',
            'main_content': '#mw-content-text, .mw-parser-output',
            'character_links': '.name a[href*="/w/"]',  # Character links in overview pages
            'character_cards': '.operator-card, .character-card',  # Character card containers
            'navigation': '.navbox, .navigation-box',
            'sidebar': '#mw-panel, .sidebar',
        }
        
        # Character page identification will be based on content, not URL patterns
        # since PRTS character URLs are URL-encoded and don't have distinguishing features
    
    async def _ensure_js_renderer(self):
        """Ensure JavaScript renderer is initialized."""
        if self.use_js_renderer and not self.js_renderer:
            self.js_renderer = JSRenderer(
                headless=True,
                timeout=30000,
                wait_for_selector=self.content_selectors['main_content'],
                wait_for_network_idle=True
            )
            await self.js_renderer.start()
    
    async def _close_js_renderer(self):
        """Close JavaScript renderer if initialized."""
        if self.js_renderer:
            await self.js_renderer.close()
            self.js_renderer = None
    

    
    async def _extract_content_async(self, url: str) -> Dict[str, Any]:
        """Async version of extract_content."""
        try:
            if self.use_js_renderer:
                await self._ensure_js_renderer()
                page_data = await self.js_renderer.render_page(url)
                html_content = page_data['html']
                page_title = page_data['title']
            else:
                response = self.make_request(url)
                html_content = response.text
                soup = BeautifulSoup(html_content, 'html.parser')
                page_title = soup.title.string if soup.title else ""
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Debug: Log page structure
            logger.debug(f"Page title: {page_title}")
            logger.debug(f"HTML content length: {len(html_content)} chars")
            
            # Extract main content
            main_content = self._extract_main_content(soup)
            logger.debug(f"Main content found: {main_content is not None}")
            if main_content:
                logger.debug(f"Main content length: {len(str(main_content))} chars")
            
            # Extract metadata
            metadata = self._extract_metadata(soup, url, page_title)
            
            # Clean and structure content
            cleaned_content = self._clean_content(main_content)
            logger.debug(f"Cleaned content length: {len(cleaned_content)} chars")
            
            # If cleaned content is empty, try alternative extraction methods
            if not cleaned_content.strip():
                logger.warning(f"No content extracted with standard method, trying alternatives...")
                cleaned_content = self._extract_content_fallback(soup)
                logger.info(f"Alternative extraction result: {len(cleaned_content)} chars")
            
            result = {
                'url': url,
                'title': page_title,
                'content': cleaned_content,
                'raw_html': str(main_content) if main_content else "",
                'metadata': metadata,
                'content_type': self._determine_content_type(url, soup),
                'extracted_at': self._get_timestamp(),
            }
            
            logger.info(f"Successfully extracted content from: {page_title}")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            raise ScrapingError(f"Failed to extract content: {e}")
    

    
    async def _extract_links_async(self, url: str) -> List[str]:
        """Async version of extract_links."""
        try:
            if self.use_js_renderer:
                await self._ensure_js_renderer()
                # Use our enhanced link extraction logic instead of simple selector
                page_data = await self.js_renderer.render_page(url)
                soup = BeautifulSoup(page_data['html'], 'html.parser')
                links = self._extract_links_from_soup(soup, url)
            else:
                response = self.make_request(url)
                soup = BeautifulSoup(response.text, 'html.parser')
                links = self._extract_links_from_soup(soup, url)
            
            # For link extraction, we need to fetch and analyze each page
            # This is more resource-intensive but more accurate
            character_links = await self._filter_character_links(links)
            
            logger.info(f"Found {len(character_links)} character links")
            return character_links
            
        except Exception as e:
            logger.error(f"Error extracting links from {url}: {e}")
            raise ScrapingError(f"Failed to extract links: {e}")
    
    def _extract_links_from_soup(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        """Extract links using BeautifulSoup with multiple fallback strategies."""
        links = []
        
        # Debug: Check what content we actually have
        logger.info(f"Page title: {soup.title.string if soup.title else 'No title'}")
        main_content = soup.select_one('#mw-content-text, .mw-parser-output')
        if main_content:
            content_text = main_content.get_text()[:200] + "..." if len(main_content.get_text()) > 200 else main_content.get_text()
            logger.info(f"Main content preview: {content_text}")
        
        # Strategy 1: .name elements (most accurate for overview pages)
        name_divs = soup.select('.name')
        logger.info(f"Found {len(name_divs)} .name divs total")
        
        name_links = soup.select('.name a[href*="/w/"]')
        logger.info(f"Found {len(name_links)} links within .name divs matching /w/ pattern")
        
        if name_links:
            logger.info(f"✓ Processing {len(name_links)} character links in .name elements")
            for i, a_tag in enumerate(name_links):
                href = a_tag.get('href')
                title = a_tag.get('title', a_tag.get_text().strip())
                logger.debug(f"  Link {i+1}: href='{href}', text='{title}'")
                if href:
                    full_url = urljoin(base_url, href)
                    links.append(full_url)
                    logger.info(f"  ✓ Added: {title} -> {full_url}")
        else:
            # Debug: Check what's inside .name divs
            logger.info("No links found in .name divs, checking their content...")
            for i, name_div in enumerate(name_divs[:5]):  # Check first 5
                div_html = str(name_div)[:200]
                logger.debug(f"  .name div {i+1}: {div_html}...")
                
                # Try to find links without /w/ filter
                all_links_in_div = name_div.select('a[href]')
                logger.debug(f"    - Found {len(all_links_in_div)} total links in this div")
                for link in all_links_in_div[:2]:  # Show first 2 links
                    logger.debug(f"      - {link.get('href')} ({link.get_text().strip()})")
        
        # Strategy 2: Character cards or operator cards
        if not links:
            logger.info("No .name links found, trying character/operator cards")
            card_links = soup.select('.operator-card a[href*="/w/"], .character-card a[href*="/w/"]')
            if card_links:
                logger.info(f"✓ Found {len(card_links)} links in character cards")
                for a_tag in card_links:
                    href = a_tag.get('href')
                    if href:
                        full_url = urljoin(base_url, href)
                        links.append(full_url)
        
        # Strategy 3: Look for any div with character-like content
        if not links:
            logger.info("No card links found, searching for character containers")
            # Try various container patterns that might hold character info
            container_selectors = [
                '.smw-columnlist-container a[href*="/w/"]',
                '.wikitable a[href*="/w/"]',
                '.operator-list a[href*="/w/"]',
                '.mw-parser-output ul a[href*="/w/"]',  # Simple list format
                '.gallery a[href*="/w/"]'  # Gallery format
            ]
            
            for selector in container_selectors:
                container_links = soup.select(selector)
                if container_links:
                    logger.info(f"✓ Found {len(container_links)} links using selector: {selector}")
                    for a_tag in container_links:
                        href = a_tag.get('href')
                        if href and not any(exclude in href for exclude in 
                                          ['一览', 'Category:', 'Template:', 'Special:', 'File:', 'Help:']):
                            full_url = urljoin(base_url, href)
                            links.append(full_url)
                    break  # Use first successful selector
        
        # Strategy 4: General fallback with filtering
        if not links:
            logger.info("No container links found, using general fallback")
            all_links = soup.select('a[href*="/w/"]')
            logger.info(f"Found {len(all_links)} total /w/ links")
            
            for a_tag in all_links:
                href = a_tag.get('href')
                text = a_tag.get_text().strip()
                
                # More aggressive filtering for character-like content
                if (href and 
                    not any(exclude in href for exclude in 
                           ['一览', 'Category:', 'Template:', 'Special:', 'File:', 'Help:', 'User:', 'Talk:']) and
                    len(text) > 0 and len(text) < 20 and  # Character names are usually short
                    not href.endswith('.png') and not href.endswith('.jpg')):
                    
                    full_url = urljoin(base_url, href)
                    links.append(full_url)
                    if len(links) <= 5:  # Log first few for debugging
                        logger.debug(f"  - Potential character: {text} -> {full_url}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        logger.info(f"✓ Final result: {len(unique_links)} unique potential character links")
        return unique_links
    
    def _extract_main_content(self, soup: BeautifulSoup) -> Optional[BeautifulSoup]:
        """Extract main content area from the page."""
        # Try different selectors for main content
        for selector in [
            self.content_selectors['main_content'],
            '.mw-content-ltr',
            '#content',
            '.content'
        ]:
            content = soup.select_one(selector)
            if content:
                # Remove navigation, sidebar, and other non-content elements
                self._remove_unwanted_elements(content)
                return content
        
        # Fallback to body if no main content found
        return soup.find('body')
    
    def _remove_unwanted_elements(self, content: BeautifulSoup) -> None:
        """Remove unwanted elements from content."""
        unwanted_selectors = [
            '.navbox', '.navigation-box', '.sidebar', '.mw-editsection',
            '.printfooter', '.catlinks', '#toc', '.references',
            'script', 'style', '.mw-hidden', '.noprint'
        ]
        
        for selector in unwanted_selectors:
            for element in content.select(selector):
                element.decompose()
    
    def _clean_content(self, content: BeautifulSoup) -> str:
        """Clean and format content text."""
        if not content:
            return ""
        
        # Get text with some structure preserved
        text = content.get_text(separator='\n', strip=True)
        
        # Use enhanced text cleaning
        return self._clean_text(text)
    
    def _extract_content_fallback(self, soup: BeautifulSoup) -> str:
        """Fallback content extraction using multiple strategies."""
        logger.info("Attempting fallback content extraction...")
        
        # Try each extraction strategy in order
        strategies = [
            self._extract_by_selectors,
            self._extract_by_paragraphs,
            self._extract_from_body
        ]
        
        for strategy in strategies:
            try:
                result = strategy(soup)
                if result and len(result.strip()) > 50:
                    return result
            except Exception as e:
                logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                continue
        
        return "No content could be extracted."
    
    def _extract_by_selectors(self, soup: BeautifulSoup) -> str:
        """Extract content using fallback CSS selectors."""
        selectors = CSS_SELECTORS.get('content_text', '.mw-parser-output').split(', ')
        selectors.extend(['#mw-content-text', '#bodyContent', '#content', '.content'])
        
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                logger.info(f"Found content using selector: {selector}")
                content_copy = BeautifulSoup(str(element), 'html.parser')
                self._remove_unwanted_elements_aggressive(content_copy)
                text = content_copy.get_text(separator='\n', strip=True)
                if text:
                    return self._clean_text(text)
        return ""
    
    def _extract_by_paragraphs(self, soup: BeautifulSoup) -> str:
        """Extract content by combining paragraphs and structured elements."""
        logger.info("Trying paragraph-based extraction...")
        elements = soup.select('p, div.mw-parser-output > *, .infobox tr')
        content_parts = [
            elem.get_text(strip=True) for elem in elements
            if elem.get_text(strip=True) and len(elem.get_text(strip=True)) > 10
        ]
        
        if content_parts:
            combined = '\n\n'.join(content_parts)
            logger.info(f"Paragraph extraction result: {len(combined)} chars")
            return self._clean_text(combined)
        return ""
    
    def _extract_from_body(self, soup: BeautifulSoup) -> str:
        """Last resort: extract from body with aggressive cleanup."""
        logger.warning("Using last resort text extraction...")
        body = soup.find('body')
        if not body:
            return ""
        
        # Remove unwanted elements
        for elem in body(['script', 'style', 'nav', 'header', 'footer']):
            elem.decompose()
        
        text = body.get_text(separator='\n', strip=True)
        return self._clean_text(text) if text else ""
    
    def _remove_unwanted_elements_aggressive(self, content: BeautifulSoup) -> None:
        """More aggressive removal of unwanted elements."""
        unwanted_selectors = [
            # Navigation and UI elements
            '.navbox', '.navigation-box', '.sidebar', '.mw-editsection',
            '.printfooter', '.catlinks', '#toc', '.references',
            'script', 'style', '.mw-hidden', '.noprint',
            
            # Additional elements that might contain noise
            '.mw-jump-link', '.mw-headline', '.edit-section',
            '.reference', '.citation', '.reflist',
            '.hatnote', '.dablink', '.rellink',
            '.navbox-group', '.navbox-list',
            
            # PRTS-specific noise
            '.smw-factbox', '.smw-tooltip', 
            '.external', '.extiw',
        ]
        
        for selector in unwanted_selectors:
            for element in content.select(selector):
                element.decompose()
        
        # Also remove elements by attribute patterns
        for element in content.find_all(attrs={"class": lambda x: x and any(cls in str(x).lower() for cls in ['nav', 'menu', 'footer', 'header', 'sidebar'])}):
            element.decompose()
    
    def _clean_text(self, text: str) -> str:
        """Enhanced text cleaning with better paragraph handling."""
        if not text:
            return ""
        
        # First, normalize line breaks and spaces
        text = re.sub(r'\r\n', '\n', text)  # Normalize Windows line breaks
        text = re.sub(r'[ \t]+', ' ', text)  # Normalize spaces and tabs
        
        # Remove common wiki artifacts before processing lines
        text = re.sub(r'\[edit\]', '', text)  # Remove [edit] links
        text = re.sub(r'\^\s*', '', text)  # Remove citation markers
        text = re.sub(r'↑\s*', '', text)  # Remove up arrows
        
        # Split into lines for processing
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip completely empty lines initially
            if not line:
                continue
            
            # Skip lines that are just navigation or UI elements
            if (len(line) <= 2 or  # Very short lines (like single characters)
                line in ['目', '录', '限', '兑'] or  # Common single-character UI elements
                re.match(r'^\d+$', line) or  # Pure numbers (section numbers)
                line.startswith('Category:') or
                line.startswith('File:')):
                continue
            
            processed_lines.append(line)
        
        # Now intelligently join lines
        final_lines = []
        i = 0
        
        while i < len(processed_lines):
            current_line = processed_lines[i]
            
            # Check if current line should be merged with next line
            if (i + 1 < len(processed_lines) and 
                not self._is_standalone_line(current_line) and
                not self._is_heading_line(current_line) and
                not self._is_list_item(current_line)):
                
                next_line = processed_lines[i + 1]
                
                # Merge if next line seems like a continuation
                if (not self._is_heading_line(next_line) and
                    not self._is_list_item(next_line) and
                    len(current_line) < 100 and  # Don't merge if current line is already long
                    not current_line.endswith(('。', '！', '？', '：', '；'))):  # Don't merge complete sentences
                    
                    # Merge with appropriate spacing
                    if current_line.endswith(('，', '、')):
                        merged = current_line + next_line
                    else:
                        merged = current_line + ' ' + next_line
                    
                    processed_lines[i] = merged
                    processed_lines.pop(i + 1)
                    continue  # Don't increment i, reprocess the merged line
            
            final_lines.append(current_line)
            i += 1
        
        # Join with appropriate spacing
        result_parts = []
        for i, line in enumerate(final_lines):
            if self._is_heading_line(line):
                # Add extra spacing before headings (except first line)
                if i > 0:
                    result_parts.append('\n')
                result_parts.append(f"## {line}")
                result_parts.append('\n')
            elif self._is_list_item(line):
                result_parts.append(f"- {line}")
                result_parts.append('\n')
            else:
                result_parts.append(line)
                # Add paragraph break for long content lines
                if len(line) > 50 and i < len(final_lines) - 1:
                    result_parts.append('\n\n')
                else:
                    result_parts.append('\n')
        
        result = ''.join(result_parts)
        
        # Final cleanup
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)  # Max 2 consecutive newlines
        result = re.sub(r'[。，、；：！？]{3,}', '...', result)  # Clean repeated punctuation
        
        return result.strip()
    
    def _is_standalone_line(self, line: str) -> bool:
        """Check if line should stand alone (complete sentence/paragraph)."""
        return (len(line) > 50 or 
                line.endswith(('。', '！', '？', '：')) or
                '：' in line)
    
    def _is_heading_line(self, line: str) -> bool:
        """Check if line looks like a heading."""
        return (len(line) <= 20 and 
                not line.endswith(('，', '、', '的', '了', '着', '过')) and
                ('信息' in line or '属性' in line or '技能' in line or '天赋' in line or
                 '材料' in line or '档案' in line or '语音' in line or '模组' in line or
                 '获得' in line or '潜能' in line or '范围' in line))
    
    def _is_list_item(self, line: str) -> bool:
        """Check if line looks like a list item."""
        return (line.startswith(('•', '·', '-', '*')) or
                re.match(r'^\d+\.', line) or
                (len(line) < 50 and ('：' in line and line.count('：') == 1)))
    
    def _extract_metadata(self, soup: BeautifulSoup, url: str, title: str) -> Dict[str, Any]:
        """Extract metadata from the page."""
        metadata = {
            'source': 'prts.wiki',
            'language': 'zh-CN',  # PRTS wiki is primarily Chinese
            'url': url,
            'title': title,
            'domain': urlparse(url).netloc,
        }
        
        # Extract infobox data if present
        infobox = soup.select_one('.infobox, .character-info')
        if infobox:
            metadata['has_infobox'] = True
            # Extract key-value pairs from infobox
            infobox_data = self._parse_infobox(infobox)
            metadata.update(infobox_data)
        
        # Check for character-specific elements
        if self._is_character_page(url, soup=soup):
            metadata['content_category'] = 'character'
            metadata['character_name'] = self._extract_character_name(title, url)
        else:
            metadata['content_category'] = 'general'
        
        return metadata
    
    def _parse_infobox(self, infobox: BeautifulSoup) -> Dict[str, str]:
        """Parse structured data from infobox."""
        data = {}
        
        # Common infobox patterns
        for row in infobox.select('tr, .infobox-row'):
            cells = row.select('td, th, .infobox-label, .infobox-data')
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if key and value:
                    data[f'infobox_{key.lower().replace(" ", "_")}'] = value
        
        return data
    
    def _determine_content_type(self, url: str, soup: BeautifulSoup) -> str:
        """Determine the type of content based on URL and page structure."""
        if '干员一览' in url or 'character' in url.lower():
            return 'character_list'
        elif self._is_character_page(url, soup=soup):
            return 'character_page'
        elif soup.select('.wikitable'):
            return 'table_data'
        else:
            return 'general_page'
    
    def _extract_character_name(self, title: str, url: str) -> str:
        """Extract character name from title or URL."""
        # Remove common wiki suffixes
        title = re.sub(r'\s*-\s*PRTS.*$', '', title)
        title = re.sub(r'\s*-\s*明日方舟.*$', '', title)
        
        # Extract from URL if title is not clean
        if not title or len(title) > 50:
            url_parts = url.split('/')
            if url_parts:
                name = url_parts[-1].replace('_', ' ')
                return name
        
        return title
    
    def _is_character_page(self, url: str, soup: BeautifulSoup = None) -> bool:
        """
        Check if page represents a character page based on content structure.
        Since PRTS character URLs are URL-encoded without distinguishing features,
        we need to analyze page content to determine if it's a character page.
        """
        # First, exclude obvious non-character pages by URL
        if any(exclude in url for exclude in ['一览', 'list', 'index', 'category', 'Category:', 'Template:']):
            return False
        
        # If soup is not provided, we can only do basic URL checks
        if soup is None:
            # Basic URL pattern: /w/something (but this is not reliable)
            return '/w/' in url and url.count('/') == 4  # https://prts.wiki/w/[character]
        
        # Content-based detection for character pages
        return self._detect_character_page_by_content(soup)
    
    def _detect_character_page_by_content(self, soup: BeautifulSoup) -> bool:
        """
        Detect character page by analyzing page content structure.
        """
        # Check for character-specific elements
        character_indicators = [
            # Character infobox
            '.infobox.character',
            '.character-info', 
            '.干员信息',
            
            # Character data tables
            '.wikitable.character-data',
            '.character-table',
            
            # Character categories
            'a[href*="Category:干员"]',
            'a[href*="Category:角色"]',
            
            # Character specific sections
            '.character-profile',
            '.character-skills',
            
            # Skill and talent sections (common in character pages)
            '*[id*="技能"]',
            '*[id*="天赋"]',
            '*[id*="skill"]',
            '*[id*="talent"]',
        ]
        
        # Count how many character indicators are present
        indicator_count = 0
        for selector in character_indicators:
            if soup.select(selector):
                indicator_count += 1
        
        # If we find multiple character indicators, it's likely a character page
        if indicator_count >= 2:
            return True
            
        # Check page categories
        categories = soup.select('a[href*="Category:"]')
        character_categories = [
            '干员', '角色', 'Operator', 'Character', 
            '六星', '五星', '四星', '三星', '二星', '一星',
            '近卫', '狙击', '重装', '医疗', '辅助', '术师', '特种', '先锋'
        ]
        
        for cat_link in categories:
            cat_text = cat_link.get_text()
            if any(char_cat in cat_text for char_cat in character_categories):
                return True
        
        # Check for character-specific text patterns in content
        content_text = soup.get_text().lower()
        character_text_patterns = [
            '干员信息', '角色信息', '基础信息',
            '技能', '天赋', '精英化', '潜能提升',
            '部署费用', '再部署时间', '阻挡数',
            '攻击速度', '生命上限', '攻击力', '防御力', '法术抗性'
        ]
        
        pattern_matches = sum(1 for pattern in character_text_patterns if pattern in content_text)
        
        # If we find many character-specific terms, it's likely a character page
        return pattern_matches >= 3
    
    async def _filter_character_links(self, links: List[str]) -> List[str]:
        """
        Filter links to identify character pages.
        For overview pages, links from .name elements are already character pages.
        For other sources, we need content verification.
        """
        character_links = []
        
        # Basic URL filtering to exclude obviously non-character pages
        potential_character_links = []
        for link in links:
            if self._is_character_page(link, soup=None):  # Basic URL check only
                potential_character_links.append(link)
        
        logger.info(f"Found {len(potential_character_links)} potential character links")
        
        # If links came from .name elements in overview page, they're likely all character pages
        # We can validate a sample to confirm, rather than checking every single one
        if len(potential_character_links) > 20:  # Looks like an overview page result
            # Sample validation: check first 3 links to confirm they're character pages
            sample_links = potential_character_links[:3]
            sample_character_count = 0
            
            for link in sample_links:
                try:
                    if self.use_js_renderer:
                        await self._ensure_js_renderer()
                        page_data = await self.js_renderer.render_page(link)
                        html_content = page_data['html']
                    else:
                        response = self.make_request(link)
                        html_content = response.text
                    
                    soup = BeautifulSoup(html_content, 'html.parser')
                    
                    if self._is_character_page(link, soup=soup):
                        sample_character_count += 1
                        
                    self.add_delay()  # Be respectful
                    
                except Exception as e:
                    logger.error(f"Error checking sample link {link}: {e}")
                    continue
            
            # If majority of samples are character pages, assume all links are character pages
            if sample_character_count >= 2:  # 2/3 or better
                logger.info(f"Sample validation passed ({sample_character_count}/3). "
                           f"Treating all {len(potential_character_links)} links as character pages")
                return potential_character_links
        
        # Full validation for smaller sets or failed sample validation
        logger.info(f"Performing full validation on {len(potential_character_links)} links...")
        
        for i, link in enumerate(potential_character_links):
            try:
                # Simple HEAD request first to check if page exists
                try:
                    head_response = self.make_request(link, method='HEAD')
                    if head_response.status_code != 200:
                        continue
                except:
                    # If HEAD fails, try GET anyway
                    pass
                
                # Get page content for analysis
                if self.use_js_renderer:
                    await self._ensure_js_renderer()
                    page_data = await self.js_renderer.render_page(link)
                    html_content = page_data['html']
                else:
                    response = self.make_request(link)
                    html_content = response.text
                
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Check if this is actually a character page
                if self._is_character_page(link, soup=soup):
                    character_links.append(link)
                    logger.info(f"✓ Character page found: {link}")
                else:
                    logger.debug(f"✗ Not a character page: {link}")
                
                # Add delay between checks
                if i < len(potential_character_links) - 1:
                    self.add_delay()
                    
            except Exception as e:
                logger.error(f"Error checking link {link}: {e}")
                continue
        
        logger.info(f"Found {len(character_links)} character pages out of {len(potential_character_links)} checked")
        return character_links
    
    def is_target_page(self, url: str, content: str = None) -> bool:
        """Check if page matches our target criteria."""
        # Target both character pages and character list pages
        if '干员一览' in url or 'character' in url.lower():
            return True
            
        # For individual pages, we need content analysis
        if content:
            soup = BeautifulSoup(content, 'html.parser')
            return self._is_character_page(url, soup=soup)
        
        # Fallback to basic URL check
        return self._is_character_page(url, soup=None)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    async def scrape_character_overview(self, overview_url: str, max_pages: int = None) -> List[Dict[str, Any]]:
        """
        Scrape character overview page and extract all character pages.
        Supports pagination to scrape multiple pages of character listings.
        
        Args:
            overview_url: URL of the character overview page
            max_pages: Maximum number of character pages to scrape (not pagination pages)
            
        Returns:
            List of scraped character data
        """
        try:
            logger.info(f"Scraping character overview: {overview_url}")
            
            # Extract character links from all pages (including pagination)
            all_character_links = await self._extract_all_character_links_with_pagination(overview_url)
            
            # Limit character pages if specified
            character_links = all_character_links
            if max_pages and len(character_links) > max_pages:
                character_links = character_links[:max_pages]
                logger.info(f"Limited to {max_pages} character pages (out of {len(all_character_links)} available)")
            
            if not character_links:
                logger.warning("No character links found in overview page")
                
                # Debug: Let's see what we actually got
                logger.info("Attempting to debug the page content...")
                if self.use_js_renderer:
                    await self._ensure_js_renderer()
                    page_data = await self.js_renderer.render_page(overview_url)
                    soup = BeautifulSoup(page_data['html'], 'html.parser')
                    
                    # Log some debug info about the page structure
                    main_content = soup.select_one('#mw-content-text')
                    if main_content:
                        # Check for various possible structures
                        name_divs = main_content.select('.name')
                        all_links = main_content.select('a[href*="/w/"]')
                        tables = main_content.select('table')
                        lists = main_content.select('ul, ol')
                        
                        logger.info(f"Debug info:")
                        logger.info(f"  - .name divs found: {len(name_divs)}")
                        logger.info(f"  - Total /w/ links: {len(all_links)}")
                        logger.info(f"  - Tables found: {len(tables)}")
                        logger.info(f"  - Lists found: {len(lists)}")
                        
                        if all_links:
                            logger.info(f"  - First 5 links:")
                            for i, link in enumerate(all_links[:5]):
                                href = link.get('href', 'no-href')
                                text = link.get_text().strip()[:30]
                                logger.info(f"    {i+1}. {text} -> {href}")
                
                return []
            
            logger.info(f"Found {len(character_links)} character pages to scrape")
            
            # Scrape each character page
            results = []
            for i, link in enumerate(character_links, 1):
                try:
                    logger.info(f"Scraping character {i}/{len(character_links)}: {link}")
                    content = await self._extract_content_async(link)
                    results.append(content)
                    
                    # Add delay between requests
                    if i < len(character_links):
                        self.add_delay()
                        
                except Exception as e:
                    logger.error(f"Failed to scrape character page {link}: {e}")
                    continue
            
            logger.info(f"Successfully scraped {len(results)} character pages")
            return results
            
        except Exception as e:
            logger.error(f"Error scraping character overview: {e}")
            raise ScrapingError(f"Failed to scrape character overview: {e}")
        finally:
            await self._close_js_renderer()
    
    async def _extract_all_character_links_with_pagination(self, start_url: str) -> List[str]:
        """
        Extract character links from all pages using interactive pagination.
        
        Args:
            start_url: Starting overview page URL
            
        Returns:
            List of all character links across all pages
        """
        all_character_links = []
        max_pagination_pages = MAX_PAGINATION_PAGES  # From config
        
        logger.info(f"Starting interactive pagination from: {start_url}")
        
        if not self.use_js_renderer:
            logger.info("Enabling JS renderer for interactive pagination")
            self.use_js_renderer = True
        
        await self._ensure_js_renderer()
        
        try:
            # Create a browser page for interactive pagination
            browser = self.js_renderer._browser
            page = await browser.new_page()
            
            # Load initial page
            await page.goto(start_url)
            await page.wait_for_load_state('networkidle')
            await page.wait_for_selector('.name', timeout=SELECTOR_TIMEOUT)
            
            current_page = 1
            
            while current_page <= max_pagination_pages:
                logger.info(f"Processing pagination page {current_page}")
                
                try:
                    # Get page content
                    content = await page.content()
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Extract character links from current page
                    page_links = self._extract_links_from_soup(soup, start_url)
                    
                    if page_links:
                        all_character_links.extend(page_links)
                        # Reduced detail log
                        logger.info(f"Page {current_page}: {len(page_links)} links found")
                    else:
                        logger.debug(f"No character links found on page {current_page}")
                    
                    # Check for next page
                    next_page_num = await self._find_next_page_number(soup)
                    
                    if next_page_num and next_page_num <= max_pagination_pages:
                        # Navigate to next page by clicking
                        success = await self._navigate_to_page(next_page_num, page)
                        
                        if success:
                            current_page = next_page_num
                            # Add delay between pagination requests
                            await page.wait_for_timeout(PAGE_NAVIGATION_WAIT)
                        else:
                            logger.info(f"Could not navigate to page {next_page_num}")
                            break
                    else:
                        logger.info("No more pagination pages found")
                        break
                        
                except Exception as e:
                    logger.error(f"Error processing pagination page {current_page}: {e}")
                    break
                    
            await page.close()
            
        except Exception as e:
            logger.error(f"Error in interactive pagination: {e}")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_links = []
        for link in all_character_links:
            if link not in seen:
                seen.add(link)
                unique_links.append(link)
        
        logger.info(f"✓ Total unique character links from {current_page} pagination pages: {len(unique_links)}")
        return unique_links
    
    async def _find_next_page_url(self, current_url: str) -> Optional[str]:
        """
        Find the URL of the next pagination page.
        
        Args:
            current_url: Current page URL
            
        Returns:
            URL of next page if found, None otherwise
        """
        try:
            # Get page content to look for pagination links
            if self.use_js_renderer:
                await self._ensure_js_renderer()
                page_data = await self.js_renderer.render_page(current_url)
                soup = BeautifulSoup(page_data['html'], 'html.parser')
            else:
                response = self.make_request(current_url)
                soup = BeautifulSoup(response.text, 'html.parser')
            
            # PRTS Wiki specific: Vue.js pagination with checkbox-container divs
            current_page_num = self._extract_current_page_number(current_url, soup)
            logger.debug(f"Current page number: {current_page_num}")
            
            # Look for Vue.js pagination elements
            pagination_containers = soup.select('.checkbox-container, [data-v-31ddfa9a], [data-v-7bc26d06]')
            if pagination_containers:
                logger.info(f"Found {len(pagination_containers)} Vue.js pagination elements")
                
                # Find the next page number
                next_page_num = None
                for container in pagination_containers:
                    text = container.get_text().strip()
                    if text.isdigit():
                        page_num = int(text)
                        if current_page_num and page_num == current_page_num + 1:
                            next_page_num = page_num
                            break
                        elif not current_page_num and page_num == 2:  # If we're on page 1
                            next_page_num = page_num
                            break
                
                if next_page_num:
                    # Construct next page URL
                    if '?' in current_url:
                        base_url = current_url.split('?')[0]
                        next_url = f"{base_url}?page={next_page_num}"
                    else:
                        next_url = f"{current_url}?page={next_page_num}"
                    
                    logger.info(f"Constructed next page URL: {next_url}")
                    return next_url
            
            # Fallback to traditional pagination patterns
            next_page_selectors = [
                # MediaWiki standard pagination
                'a[rel="next"]',
                'a:contains("下一页")',
                'a:contains("下页")', 
                'a:contains("Next")',
                'a:contains("→")',
                
                # SMW (Semantic MediaWiki) pagination
                '.smw-page-nav a:contains("下一页")',
                '.smw-page-nav a:contains("Next")',
                
                # Custom pagination patterns
                '.pagination a:contains("下一页")',
                '.pagination a:contains("Next")',
                '.page-nav a:contains("下一页")',
                
                # Numbered pagination (look for next number)
                '.pagination a[title*="下一页"]',
                
                # WikiTable pagination
                '.wikitable + p a:contains("下一页")',
            ]
            
            for selector in next_page_selectors:
                try:
                    if ':contains(' in selector:
                        # Handle pseudo-selector manually
                        base_selector = selector.split(':contains(')[0]
                        contains_text = selector.split(':contains(')[1].rstrip(')')
                        contains_text = contains_text.strip('"').strip("'")
                        
                        candidates = soup.select(base_selector)
                        for candidate in candidates:
                            if contains_text in candidate.get_text():
                                href = candidate.get('href')
                                if href:
                                    from urllib.parse import urljoin
                                    next_url = urljoin(current_url, href)
                                    logger.info(f"Found next page using selector '{selector}': {next_url}")
                                    return next_url
                    else:
                        next_link = soup.select_one(selector)
                        if next_link and next_link.get('href'):
                            from urllib.parse import urljoin
                            next_url = urljoin(current_url, next_link.get('href'))
                            logger.info(f"Found next page using selector '{selector}': {next_url}")
                            return next_url
                except Exception as e:
                    logger.debug(f"Error with selector '{selector}': {e}")
                    continue
            
            # Try to find numbered pagination
            pagination_numbers = soup.select('a[href*="offset="], a[href*="page="], a[href*="from="]')
            current_page_num = self._extract_page_number_from_url(current_url)
            
            for link in pagination_numbers:
                href = link.get('href')
                if href:
                    page_num = self._extract_page_number_from_url(href)
                    if page_num and page_num == current_page_num + 1:
                        from urllib.parse import urljoin
                        next_url = urljoin(current_url, href)
                        logger.info(f"Found next page by number: {next_url}")
                        return next_url
            
            logger.debug("No next page link found")
            return None
            
        except Exception as e:
            logger.error(f"Error finding next page URL: {e}")
            return None
    
    def _extract_current_page_number(self, url: str, soup: BeautifulSoup) -> Optional[int]:
        """Extract current page number from URL or page content."""
        try:
            # First try to get from URL parameters
            page_num = self._extract_page_number_from_url(url)
            if page_num:
                return page_num
            
            # For PRTS Wiki, look for selected page indicator
            selected_containers = soup.select('.selected.checkbox-container, .checkbox-container.selected')
            if selected_containers:
                for container in selected_containers:
                    text = container.get_text().strip()
                    if text.isdigit():
                        return int(text)
            
            # Look for active page indicators
            active_elements = soup.select('.active, .current, [class*="current"], [class*="active"]')
            for elem in active_elements:
                text = elem.get_text().strip()
                if text.isdigit():
                    return int(text)
            
            # If no page indicator found, assume page 1
            return 1
        except Exception:
            return 1
    
    def _extract_page_number_from_url(self, url: str) -> Optional[int]:
        """Extract page number from URL parameters."""
        try:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # Common pagination parameters
            for param in ['page', 'offset', 'from', 'start']:
                if param in params:
                    try:
                        return int(params[param][0])
                    except (ValueError, IndexError):
                        continue
            
            return None
        except Exception:
            return None
    
    async def _find_next_page_number(self, soup: BeautifulSoup) -> Optional[int]:
        """Find the next available page number from pagination elements."""
        try:
            # Get current page number
            current_page = self._extract_current_page_number_from_soup(soup)
            
            # Look for pagination containers
            pagination_containers = soup.select('.checkbox-container')
            
            # Find available page numbers
            available_pages = []
            for container in pagination_containers:
                text = container.get_text().strip()
                if text.isdigit():
                    page_num = int(text)
                    if page_num <= 20:  # Reasonable page limit
                        available_pages.append(page_num)
            
            available_pages = sorted(set(available_pages))
            logger.debug(f"Current page: {current_page}, Available pages: {available_pages}")
            
            # Find next page
            next_page = current_page + 1
            if next_page in available_pages:
                logger.debug(f"Next page available: {next_page}")
                return next_page
            
        except Exception as e:
            logger.error(f"Error finding next page: {e}")
        
        return None
    
    def _extract_current_page_number_from_soup(self, soup: BeautifulSoup) -> int:
        """Extract current page number from soup (selected pagination element)."""
        try:
            # Check for selected pagination element
            selected_elements = soup.select('.checkbox-container.selected')
            for element in selected_elements:
                text = element.get_text().strip()
                if text.isdigit():
                    return int(text)
                    
            return 1  # Default to page 1
        except Exception as e:
            logger.error(f"Error extracting current page from soup: {e}")
            return 1
    

    
    async def _navigate_to_page(self, page_number: int, page_obj) -> bool:
        """Navigate to a specific page using JavaScript DOM manipulation."""
        try:
            # Wait for pagination to be loaded
            await page_obj.wait_for_selector('.paginations-container', timeout=SELECTOR_TIMEOUT)
            
            # Get current page before navigation
            before_page = await page_obj.evaluate('''
                () => {
                    const selected = document.querySelector('.paginations-container .checkbox-container.selected');
                    return selected ? parseInt(selected.textContent.trim()) : 1;
                }
            ''')
            
            logger.debug(f"Attempting to navigate from page {before_page} to page {page_number}")
            
            # Use JavaScript to find and click the correct pagination element
            navigation_success = await page_obj.evaluate(f'''
                (targetPage) => {{
                    // Find all pagination containers
                    const paginationContainers = document.querySelectorAll('.paginations-container');
                    
                    for (let container of paginationContainers) {{
                        // Find the target page element in this container
                        const pageElements = container.querySelectorAll('.checkbox-container');
                        
                        for (let element of pageElements) {{
                            const text = element.textContent.trim();
                            
                            // Check if this is our target page and not already selected
                            if (text === targetPage.toString() && !element.classList.contains('selected')) {{
                                // Store original character count to detect changes
                                const beforeCount = document.querySelectorAll('.name').length;
                                
                                // Click the element
                                element.scrollIntoView();
                                element.click();
                                
                                // Return info for verification
                                return {{
                                    clicked: true,
                                    element: element.textContent,
                                    container: container.className,
                                    beforeCount: beforeCount
                                }};
                            }}
                        }}
                    }}
                    
                    return {{ clicked: false, reason: 'Element not found or already selected' }};
                }}
            ''', page_number)
            
            if not navigation_success.get('clicked'):
                logger.error(f"Could not click page {page_number}: {navigation_success.get('reason')}")
                return False
            
            # Removed detailed click info log
            
            # Wait for content to change with multiple strategies
            max_wait_time = 10  # seconds
            wait_interval = 0.5  # seconds
            elapsed = 0
            
            while elapsed < max_wait_time:
                await page_obj.wait_for_timeout(int(wait_interval * 1000))
                elapsed += wait_interval
                
                # Check if page has changed
                current_state = await page_obj.evaluate('''
                    () => {
                        const selected = document.querySelector('.paginations-container .checkbox-container.selected');
                        const characterCount = document.querySelectorAll('.name').length;
                        return {
                            currentPage: selected ? parseInt(selected.textContent.trim()) : 1,
                            characterCount: characterCount
                        };
                    }
                ''')
                
                current_page = current_state.get('currentPage', 1)
                character_count = current_state.get('characterCount', 0)
                
                if current_page == page_number:
                    # Reduced detail log
                    logger.info(f"✓ Page {page_number} loaded")
                    return True
                elif current_page != before_page:
                    logger.warning(f"Navigation landed on page {current_page} instead of {page_number}")
                    return False
            
            logger.warning(f"Navigation timeout: still on page {before_page} after {max_wait_time}s")
            return False
                
        except Exception as e:
            logger.error(f"Error navigating to page {page_number}: {e}")
            return False
    
    # Implementation of abstract methods from BaseScraper
    def extract_content(self, url: str) -> Dict[str, Any]:
        """Synchronous wrapper for content extraction (required by abstract base class)."""
        return asyncio.run(self._extract_content_async(url))
    
    def extract_links(self, url: str) -> List[str]:
        """Synchronous wrapper for link extraction (required by abstract base class)."""
        return asyncio.run(self._extract_links_async(url))
    
    def is_target_page(self, url: str, content: str = None) -> bool:
        """Determine if a page is a character page."""
        if content:
            soup = BeautifulSoup(content, 'html.parser')
            return self._is_character_page(url, soup=soup)
        return self._is_character_page(url, soup=None)
    
