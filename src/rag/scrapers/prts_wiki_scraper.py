"""PRTS Wiki scraper for character information and related content."""

import asyncio
import logging
import re
import time
from typing import List, Dict, Any, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .base_scraper import BaseScraper, ScrapingError
from ..extractors.js_renderer import JSRenderer
from .attack_range_parser import AttackRangeParser
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
        """Ensure JavaScript renderer is initialized with enhanced waiting configuration."""
        if self.use_js_renderer and not self.js_renderer:
            # Create a comprehensive selector list that covers various PRTS Wiki content patterns
            comprehensive_selectors = ','.join([
                # Primary content selectors
                self.content_selectors['main_content'],
                self.content_selectors.get('character_info', ''),
                self.content_selectors.get('character_list', ''),
                # Common content containers
                '.main-content',
                '.wiki-content',
                '#mw-content-text',
                '.article-content',
                '#content',
                # Common text elements that indicate content is loaded
                '.mw-parser-output',
                '.smw-columnlist-container',
                '.tab-content',
                '.tab-pane.active',
                # Character specific elements
                '.name',
                '.operator-card',
                '.character-card',
                '.charbox',
                # Content markers
                'p:not(:empty)',
                'h1:not(:empty)',
                'h2:not(:empty)',
                'h3:not(:empty)',
                '.section:not(:empty)'
            ])
            
            # Remove empty selectors
            comprehensive_selectors = ','.join([s.strip() for s in comprehensive_selectors.split(',') if s.strip()])
            
            logger.info(f"Initializing JS renderer with enhanced waiting configuration")
            
            # Create renderer with optimized settings
            self.js_renderer = JSRenderer(
                headless=True,
                timeout=45000,  # Increased timeout for slow-loading pages
                wait_for_selector=comprehensive_selectors,
                wait_for_network_idle=True,
                viewport_size={'width': 1920, 'height': 1080}  # Larger viewport for better content capture
            )
            await self.js_renderer.start()
            logger.info(f"JS renderer initialized successfully with comprehensive selectors")
    
    async def _close_js_renderer(self):
        """Close JavaScript renderer if initialized."""
        if self.js_renderer:
            await self.js_renderer.close()
            self.js_renderer = None
    

    
    async def _extract_content_async(self, url: str) -> Dict[str, Any]:
        """Async version of extract_content."""
        extraction_start_time = time.time()
        try:
            if self.use_js_renderer:
                await self._ensure_js_renderer()

                # Enhanced page rendering with custom waiting options
                page_data = await self.js_renderer.render_page(
                    url,
                    wait_for_function="() => document.readyState === 'complete'"
                )

                html_content = page_data['html']
                page_title = page_data['title']

                # **NEW**: 滚动页面以触发攻击范围SVG和其他懒加载内容
                if hasattr(self.js_renderer, 'scroll_and_wait'):
                    # 创建临时page对象进行滚动
                    page = await self.js_renderer._context.new_page()
                    try:
                        await page.set_content(html_content)
                        await self.js_renderer.scroll_and_wait(page, scroll_pause=2.0, max_scrolls=3)

                        # **NEW**: 等待攻击范围SVG生成
                        if self._is_character_page(url, soup=None):
                            attack_range_selectors = [
                                'svg',  # 任何SVG元素
                                '.infobox svg',  # infobox中的SVG
                                '.charbox svg',  # charbox中的SVG
                            ]

                            svg_found = False
                            for selector in attack_range_selectors:
                                try:
                                    # 等待SVG出现，10秒超时
                                    await page.wait_for_selector(selector, timeout=10000)
                                    svg_found = True

                                    # 额外等待确保SVG完全渲染
                                    await page.wait_for_timeout(2000)
                                    break
                                except PlaywrightTimeoutError:
                                    continue

                        # **NEW**: 等待技能表格加载完成
                        if self._is_character_page(url, soup=None):
                            table_selectors = [
                                'table.wikitable',
                                'table',
                                '.wikitable',
                                '#mw-content-text table'
                            ]

                            for selector in table_selectors:
                                try:
                                    # 等待表格出现，15秒超时
                                    await page.wait_for_selector(selector, timeout=15000)
                                    logger.debug(f"Table loaded with selector: {selector}")
                                    # 额外等待确保表格数据完全渲染
                                    await page.wait_for_timeout(3000)
                                    break
                                except PlaywrightTimeoutError:
                                    logger.debug(f"Table selector not found: {selector}")
                                    continue

                        # 获取滚动后的HTML内容
                        html_content = await page.content()
                    finally:
                        await page.close()

            else:
                response = self.make_request(url)
                html_content = response.text
                soup = BeautifulSoup(html_content, 'html.parser')
                page_title = soup.title.string if soup.title else ""

            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')

            # Check for specific content patterns
            has_tables = len(soup.find_all('table')) > 0
            has_lists = len(soup.find_all(['ul', 'ol'])) > 0
            has_headings = len(soup.find_all(['h1', 'h2', 'h3'])) > 0

            # Extract main content
            main_content = self._extract_main_content(soup)
            main_content_str = str(main_content) if main_content else ""
            main_content_length = len(main_content_str)

            # Extract metadata
            metadata = self._extract_metadata(soup, url, page_title)

            # Determine content type
            content_type = self._determine_content_type(url, soup)

            # Special handling for pages with tables (both table_data and character_page)
            if content_type in ['table_data', 'character_page'] and soup.find_all('table'):
                table_content = self._extract_from_tables(soup)
                if table_content and len(table_content.strip()) > 100 and '|' in table_content:  # Check for pipe chars in table content
                    # Combine table content with a portion of regular content
                    regular_content = self._clean_content(main_content)
                    # Extract first 1000 chars of regular content as introduction
                    intro_content = regular_content[:1000].split('\n')[:10]  # Get first 10 lines or 1000 chars
                    intro_content = '\n'.join(intro_content)
                    # Combine intro and tables
                    cleaned_content = f"{intro_content}\n\n## 详细数据表格\n\n{table_content}"
                else:
                    cleaned_content = self._clean_content(main_content)
            else:
                # Standard content cleaning and structuring
                cleaned_content = self._clean_content(main_content)

            cleaned_content_length = len(cleaned_content)
            cleaned_content_lines = len(cleaned_content.strip().split('\n'))

            # If cleaned content is empty or insufficient, try alternative extraction methods
            if not cleaned_content.strip() or (content_type == 'table_data' and '|' not in cleaned_content):
                cleaned_content = self._extract_content_fallback(soup)

            # Final content quality assessment
            final_content_length = len(cleaned_content)
            final_content_words = len(cleaned_content.split())
            content_quality = "EXCELLENT" if final_content_length > 1000 else "GOOD" if final_content_length > 500 else "MINIMAL" if final_content_length > 100 else "POOR"

            # Calculate total extraction time
            extraction_time = time.time() - extraction_start_time

            # Create detailed result with extraction metadata
            result = {
                'url': url,
                'title': page_title,
                'content': cleaned_content,
                'raw_html': str(main_content) if main_content else "",
                'metadata': metadata,
                'content_type': self._determine_content_type(url, soup),
                'extracted_at': self._get_timestamp(),
                # Add extraction metrics for debugging
                'extraction_stats': {
                    'processing_time_seconds': round(extraction_time, 2),
                    'content_length_chars': final_content_length,
                    'content_lines': cleaned_content_lines,
                    'content_quality_estimate': content_quality,
                    'js_rendering_used': self.use_js_renderer
                }
            }

            return result

        except Exception as e:
            extraction_time = time.time() - extraction_start_time
            logger.error(f"ERROR extracting content from {url} (after {extraction_time:.2f}s): {e}", exc_info=True)

            # Log specific error details for common scraping issues
            if 'timeout' in str(e).lower():
                logger.error(f"Timeout error suggests page loading issues for {url}")
            elif 'selector' in str(e).lower():
                logger.error(f"Selector error suggests page structure may have changed for {url}")
            elif 'network' in str(e).lower():
                logger.error(f"Network error suggests connectivity issues for {url}")

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
        logger.debug(f"Page title: {soup.title.string if soup.title else 'No title'}")
        main_content = soup.select_one('#mw-content-text, .mw-parser-output')
        
        # Strategy 1: .name elements (most accurate for overview pages)
        name_divs = soup.select('.name')
        logger.info(f"Found {len(name_divs)} .name divs total")
        
        name_links = soup.select('.name a[href*="/w/"]')
        logger.info(f"Found {len(name_links)} links within .name divs matching /w/ pattern")
        
        if name_links:
            logger.info(f"✓ Processing {len(name_links)} character links")
            for i, a_tag in enumerate(name_links):
                href = a_tag.get('href')
                if href:
                    full_url = urljoin(base_url, href)
                    links.append(full_url)
        else:
            # Debug: Check what's inside .name divs (simplified)
            logger.warning("No links found in .name divs, trying alternative selectors...")
            for i, name_div in enumerate(name_divs[:3]):  # Check first 3 only
                # Try to find links without /w/ filter
                all_links_in_div = name_div.select('a[href]')
                if all_links_in_div:
                    logger.debug(f"  .name div {i+1}: Found {len(all_links_in_div)} links")
        
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
        """Extract main content area from the page with enhanced selector options."""
        # Enhanced list of selectors for main content
        selectors = [
            # Primary selectors
            self.content_selectors['main_content'],
            
            # Wiki-specific selectors
            '.mw-content-ltr',
            '#content',
            '.content',
            
            # Secondary selectors
            '.mw-body-content',
            '#mw-content-text .mw-parser-output',
            '#content-wrapper',
            '.content-container',
            '.article-content',
            
            # PRTS-specific selectors
            '.main-container',
            '.wiki-content',
            '#content-inner',
            '.wiki-article',
            
            # Table-based content (common in wikis)
            '.wikitable',
            '.character-info',
            '.infobox',
            
            # Container-based selectors
            '.container',
            '.main',
            'main',
            '.article',
            'article'
        ]
        
        # Try each selector
        for selector in selectors:
            content = soup.select_one(selector)
            if content and content.get_text(strip=True):
                logger.debug(f"Found content using selector: {selector}")
                # Remove navigation, sidebar, and other non-content elements
                self._remove_unwanted_elements(content)
                return content
        
        logger.warning("No main content found with primary selectors, trying paragraph aggregation")
        
        # Alternative approach: aggregate meaningful paragraphs
        paragraphs = soup.find_all('p')
        if paragraphs:
            # Create a new container to hold meaningful paragraphs
            content_container = soup.new_tag('div')
            meaningful_paragraphs = 0
            
            for p in paragraphs:
                text = p.get_text(strip=True)
                # Only add paragraphs with substantial content
                if len(text) > 20:  # Skip very short paragraphs that are likely navigation
                    content_container.append(p)
                    meaningful_paragraphs += 1
            
            if meaningful_paragraphs > 0:
                logger.debug(f"Aggregated {meaningful_paragraphs} meaningful paragraphs")
                self._remove_unwanted_elements(content_container)
                return content_container
        
        # Final fallback to body if no other content found
        logger.warning("No meaningful content found, falling back to body")
        body = soup.find('body')
        if body:
            # For body fallback, be more careful about what to remove
            # We don't want to remove too much from the body
            for selector in ['.navbox', '.navigation-box', 'script', 'style', 'nav', 'header', 'footer']:
                for element in body.select(selector):
                    element.decompose()
        
        return body
    
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
        """Enhanced fallback content extraction using multiple strategies."""
        logger.info("Attempting enhanced fallback content extraction...")
        
        # Try each extraction strategy in order with lower thresholds
        strategies = [
            self._extract_by_selectors,
            self._extract_by_paragraphs,
            self._extract_from_body,
            self._extract_from_tables,  # New strategy
            self._extract_from_headings  # New strategy
        ]
        
        # Collect all successful results
        results = []
        
        for strategy in strategies:
            try:
                result = strategy(soup)
                if result and len(result.strip()) > 30:  # Lower threshold for fallback
                    logger.debug(f"Strategy {strategy.__name__} succeeded with {len(result.strip())} chars")
                    results.append((len(result.strip()), result))
            except Exception as e:
                logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                continue
        
        # If we have results, return the longest one
        if results:
            results.sort(reverse=True, key=lambda x: x[0])  # Sort by length
            logger.info(f"Best fallback strategy returned {results[0][0]} chars")
            return results[0][1]
        
        # Final resort: very minimal extraction
        logger.warning("All strategies failed, attempting minimal extraction...")
        minimal_text = soup.get_text(separator='\n', strip=True)
        if minimal_text and len(minimal_text.strip()) > 20:
            return minimal_text.strip()[:1000]  # Return at least some content
            
        return "[Content extraction produced limited results]"
    
    def _extract_by_selectors(self, soup: BeautifulSoup) -> str:
        """Enhanced content extraction using comprehensive CSS selectors."""
        # Start with configured selectors
        selectors = CSS_SELECTORS.get('content_text', '.mw-parser-output').split(', ')
        
        # Add common wiki content selectors
        selectors.extend([
            # MediaWiki standard selectors
            '#mw-content-text', '#bodyContent', '#content', '.content',
            
            # PRTS-specific selectors
            '.wiki-article', '.wiki-page', '.article-content',
            '.entry-content', '.wiki-text', '.wiki-content-wrapper',
            '#mw-content-text', '#contentSub', '.mw-headline',
            
            # Chinese wiki common containers
            '.wiki-body', '.wiki-content-inner', '.article-body',
            '.content-section', '.wiki-section',
            
            # Table content
            'table.wikitable', 'table.info-table', 'table.data-table',
            
            # Content blocks
            'div[id^="section-"]', 'div[id^="content-"]',
            'article', 'main', 'section', 'div.content-wrapper',
            
            # Additional common selectors
            '.post-content', '.article-body', '.body-content',
            '.content-main', '.content-inner', '.content-container'
        ])
        
        # Try each selector and collect potential content
        best_result = ""
        best_length = 0
        
        for selector in selectors:
            try:
                # Try select_one for single elements
                element = soup.select_one(selector)
                if element:
                    content_copy = BeautifulSoup(str(element), 'html.parser')
                    # Use less aggressive cleaning for fallback
                    self._remove_unwanted_elements(content_copy)  # Note: Using regular removal instead of aggressive
                    text = content_copy.get_text(separator='\n', strip=True)
                    
                    if text and len(text) > best_length:
                        logger.debug(f"Found better content using selector: {selector} ({len(text)} chars)")
                        best_result = text
                        best_length = len(text)
                
                # Also try select for multiple elements (might find more content)
                elements = soup.select(selector)
                if len(elements) > 1:
                    combined_text = []
                    for elem in elements:
                        content_copy = BeautifulSoup(str(elem), 'html.parser')
                        self._remove_unwanted_elements(content_copy)
                        elem_text = content_copy.get_text(separator='\n', strip=True)
                        if elem_text:
                            combined_text.append(elem_text)
                    
                    combined = '\n\n'.join(combined_text)
                    if combined and len(combined) > best_length:
                        logger.debug(f"Found better combined content using selector: {selector} ({len(combined)} chars)")
                        best_result = combined
                        best_length = len(combined)
            except Exception as e:
                logger.debug(f"Error with selector {selector}: {e}")
                continue
        
        if best_result:
            logger.info(f"Best selector extraction result: {best_length} chars")
            return self._clean_text(best_result)
            
        return ""
    
    def _extract_by_paragraphs(self, soup: BeautifulSoup) -> str:
        """Enhanced paragraph-based content extraction."""
        logger.info("Trying enhanced paragraph-based extraction...")
        
        # Look for various content elements, not just paragraphs
        elements_to_try = [
            ('p', 20),  # Paragraphs with slightly higher threshold
            ('div', 30),  # Divs with meaningful content
            ('section', 50),  # Section elements
            (['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], 10),  # Headings with lower threshold
            ('li', 15),  # List items
            ('.infobox tr', 25),  # Info box table rows
        ]
        
        content_parts = []
        
        for selector, min_length in elements_to_try:
            try:
                elements = soup.select(selector) if isinstance(selector, str) else soup.find_all(selector)
                for elem in elements:
                    # Skip elements that are likely navigation or noise
                    skip = False
                    for class_name in ['nav', 'menu', 'sidebar', 'footer', 'editsection']:
                        if class_name in elem.get('class', []) or class_name in str(elem.get('id', '')):
                            skip = True
                            break
                    
                    if skip:
                        continue
                    
                    text = elem.get_text(strip=True)
                    # Use the specified minimum length threshold
                    if text and len(text) >= min_length:
                        # For headings, format them appropriately
                        if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            level = int(elem.name[1])
                            content_parts.append(f"{'#' * min(level, 3)} {text}")
                        else:
                            content_parts.append(text)
            except Exception as e:
                logger.debug(f"Error extracting {selector}: {e}")
                continue
        
        if content_parts:
            # Join with appropriate spacing
            combined = '\n\n'.join(content_parts)
            logger.info(f"Enhanced paragraph extraction result: {len(combined)} chars")
            return self._clean_text(combined)
        return ""
    
    def _extract_from_body(self, soup: BeautifulSoup) -> str:
        """Enhanced body content extraction with smarter cleanup."""
        logger.warning("Using enhanced body text extraction...")
        body = soup.find('body')
        if not body:
            return ""
        
        # Create a deep copy to avoid modifying the original
        body_copy = BeautifulSoup(str(body), 'html.parser')
        
        # First, remove definitely unwanted elements
        for tag in ['script', 'style', 'iframe', 'noscript', 'svg']:
            for elem in body_copy(tag):
                elem.decompose()
        
        # Then remove navigation and UI elements but more selectively
        for elem in body_copy.find_all(['div', 'header', 'nav', 'footer', 'aside', 'form']):
            # Check if element is likely navigation/UI based on classes and IDs
            is_unwanted = False
            class_list = elem.get('class', [])
            id_name = elem.get('id', '')
            
            # List of suspicious class patterns
            suspicious_classes = ['nav', 'menu', 'sidebar', 'footer', 'header', 
                                 'breadcrumb', 'toolbar', 'login', 'register',
                                 'user', 'search', 'advert', 'banner', 'popup',
                                 'social', 'share', 'comment']
            
            # List of suspicious ID patterns
            suspicious_ids = ['nav', 'menu', 'sidebar', 'footer', 'header',
                             'breadcrumb', 'toolbar', 'login', 'search',
                             'advert', 'banner', 'comments']
            
            # Check classes
            for cls in class_list:
                if any(suspicious in cls.lower() for suspicious in suspicious_classes):
                    is_unwanted = True
                    break
            
            # Check ID if classes didn't trigger
            if not is_unwanted and id_name:
                is_unwanted = any(suspicious in id_name.lower() for suspicious in suspicious_ids)
            
            # Only remove if we're confident it's unwanted
            if is_unwanted:
                elem.decompose()
        
        # Extract text with structure preserved
        text = body_copy.get_text(separator='\n', strip=True)
        
        # For body extraction, use minimal cleaning to preserve as much as possible
        if text:
            # Only apply basic normalization
            lines = text.split('\n')
            # Keep lines that have at least some meaningful content
            meaningful_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 5]
            cleaned = '\n'.join(meaningful_lines)
            logger.info(f"Body extraction result: {len(cleaned)} chars")
            # Apply text cleaning to format【tags】
            return self._clean_text(cleaned)

        return ""
    
    def _remove_unwanted_elements_aggressive(self, content: BeautifulSoup) -> None:
        """More aggressive but selective removal of unwanted elements."""
        # First, define a safer version for fallback content
        unwanted_selectors = [
            # Navigation and UI elements (definitely safe to remove)
            'script', 'style', 'iframe', 'noscript',
            '.mw-editsection', '.edit-section',
            '.printfooter', '.noprint', '.mw-hidden',
            
            # Citation elements
            '.reference', '.citation', '.reflist', '.references',
            
            # Some navigation elements
            '.navbox', '.navigation-box', '.breadcrumb',
            '.navbox-group', '.navbox-list',
            
            # PRTS-specific noise
            '.smw-factbox', '.smw-tooltip', 
            '.external', '.extiw',
        ]
        
        # Remove elements that are definitely unwanted
        for selector in unwanted_selectors:
            for element in content.select(selector):
                element.decompose()
        
        # Also remove elements by attribute patterns
        for element in content.find_all(attrs={"class": lambda x: x and any(cls in str(x).lower() for cls in ['nav', 'menu', 'footer', 'header', 'sidebar'])}):
            element.decompose()
        
        # Add two new extraction methods
    def _extract_from_tables(self, soup: BeautifulSoup) -> str:
        """Extract structured data from tables with improved formatting and organization."""
        logger.info("Trying optimized table-based extraction...")
        tables = soup.find_all('table')

        # **NEW**: Add detailed logging for debugging
        logger.info(f"Found {len(tables)} tables on page")

        if not tables:
            logger.debug("No tables found, skipping table extraction")
            return ""

        table_contents = []
        processed_tables = []  # Track processed tables to avoid duplicates

        # Helper function to calculate table hash for duplicate detection
        def calculate_table_hash(table):
            """Calculate a hash for the table content to detect duplicates."""
            import hashlib
            import re

            # Extract all cell text
            cells = table.find_all(['td', 'th'])
            cell_texts = [cell.get_text(strip=True) for cell in cells]

            # Join all text and normalize
            table_text = '|'.join(sorted(cell_texts))  # Sort for consistency

            # Create hash
            return hashlib.md5(table_text.encode('utf-8')).hexdigest()

        # Helper function to get table context for better titling
        def get_table_context(table, index):
            # Look for preceding heading
            prev_elem = table.find_previous(['h2', 'h3', 'h4'])
            if prev_elem:
                heading_text = prev_elem.get_text(strip=True)
                return f"{heading_text} - 表格 {index + 1}"
            
            # Look for table caption
            caption = table.find('caption')
            if caption:
                caption_text = caption.get_text(strip=True)
                return f"{caption_text}"
            
            # Use class/id for better identification
            table_classes = table.get('class', [])
            table_id = table.get('id', '')
            if table_classes:
                return f"{', '.join(table_classes)} - 表格 {index + 1}"
            if table_id:
                return f"{table_id} - 表格 {index + 1}"
            
            return f"表格 {index + 1}"
        
        # Helper function to determine table priority
        def get_table_priority(table):
            # Base priority
            priority = 10
            
            # Increase priority for tables with IDs or specific classes
            table_id = table.get('id', '')
            table_classes = table.get('class', [])
            
            # Higher priority for infobox-like tables
            if any(keyword in str(table_id).lower() or keyword in ' '.join(table_classes).lower() 
                   for keyword in ['infobox', 'data', 'stat', '属性']):
                priority -= 5
            
            # Higher priority for tables with more rows
            rows = table.find_all('tr')
            if len(rows) > 5:
                priority -= 2
            
            # Lower priority for tables that look like navigation
            if any(keyword in str(table_id).lower() or keyword in ' '.join(table_classes).lower() 
                   for keyword in ['nav', 'menu', 'pagination']):
                priority += 10
            
            return priority
        
        # Get all tables with their priority
        tables_with_priority = [(table, get_table_priority(table)) for table in tables]
        # Sort tables by priority (lower number = higher priority)
        tables_with_priority.sort(key=lambda x: x[1])
        
        for i, (table, _) in enumerate(tables_with_priority):
            # **NEW**: Log table processing with contextual info
            table_title = get_table_context(table, i)
            table_rows = table.find_all('tr')
            logger.debug(f"Processing table {i+1}/{len(tables_with_priority)}: {table_title[:50]} ({len(table_rows)} rows)")

            # Skip tables that look like navigation or UI
            skip = False
            for class_name in ['nav', 'menu', 'sidebar', 'footer', 'pagination']:
                if class_name in table.get('class', []) or class_name in str(table.get('id', '')):
                    skip = True
                    break
            
            if skip:
                logger.debug(f"Skipping navigation/UI table: {table_title[:50]}")
                continue
            
            # Try to extract table data
            rows = table.find_all('tr')
            if not rows or len(rows) < 1:  # Allow single row tables for data like infoboxes
                continue
            
            table_text = []
            
            # Get and add table context/title
            table_title = get_table_context(table, i)
            table_text.append(f"## {table_title}")
            table_text.append("")  # Add blank line after title
            
            # Improved table parsing logic
            has_header = False
            header_count = 0
            
            # First pass to check for headers and determine structure
            for row in rows:
                th_cells = row.find_all('th')
                if th_cells and any(th.get_text(strip=True) for th in th_cells):
                    has_header = True
                    header_count = max(header_count, len(th_cells))
            
            # Process each row with better structure preservation
            first_data_row_processed = False
            header_added = False
            for row_idx, row in enumerate(rows):
                # Extract both th and td cells
                cells = row.find_all(['td', 'th'])

                # **IMPROVED**: Enhanced cell extraction with fallback to raw HTML
                cell_texts = []
                for cell in cells:
                    # Try to get text content
                    text = cell.get_text(strip=True)

                    # **NEW**: If text is empty, fall back to raw HTML content
                    if not text:
                        # Check for image alt text
                        img_alt = cell.find('img', alt=True)
                        if img_alt:
                            text = img_alt.get('alt', '').strip()

                        # Check for data attributes
                        if not text:
                            data_value = cell.get('data-value') or cell.get('data-content')
                            if data_value:
                                text = str(data_value).strip()

                        # Final fallback: use stripped HTML if still empty
                        if not text:
                            html_content = str(cell)
                            # Extract text from HTML tags manually
                            import re
                            text_match = re.search(r'>([^<]+)<', html_content)
                            if text_match:
                                text = text_match.group(1).strip()

                    cell_texts.append(text)

                # Skip empty rows (but log for debugging)
                if not any(cell_texts):
                    logger.debug(f"Skipping empty row {row_idx} in table")
                    continue

                # Fix truncated data in cells (e.g., "48 2" -> "48 | 2")
                fixed_cell_texts = []
                for cell_text in cell_texts:
                    # Check if this looks like truncated data (number followed by space and another number)
                    import re
                    # Pattern: digits followed by space and digits, possibly with "→" in between
                    if re.match(r'^\d+\s+\d+$', cell_text) or re.match(r'^\d+→\d+$', cell_text):
                        # Replace space with pipe separator
                        fixed_text = cell_text.replace(' ', ' | ')
                        fixed_text = fixed_text.replace('→', ' → ')
                        fixed_cell_texts.append(fixed_text)
                    else:
                        fixed_cell_texts.append(cell_text)

                # Handle header row(s) - only add once
                if row.find_all('th') and not header_added:
                    # Add header row
                    table_text.append(" | ".join(fixed_cell_texts))
                    # Create proper separator row that matches the number of columns
                    # Only add separator if we have multiple columns
                    if len(fixed_cell_texts) > 1:
                        separator = ["---"] * len(fixed_cell_texts)
                        table_text.append(" | ".join(separator))
                    has_header = True
                    header_added = True
                    first_data_row_processed = True
                else:
                    # Regular data row
                    # **IMPROVED**: Allow all non-empty rows (even single characters)
                    if len(' '.join(fixed_cell_texts)) > 0:  # Only skip completely empty rows
                        table_text.append(" | ".join(fixed_cell_texts))
                    first_data_row_processed = True
            
            # Only add tables with meaningful content
            # More permissive condition - allow tables with at least one data row
            non_empty_rows = [row for row in table_text if row.strip() and not row.startswith('#') and row != '---']
            if len(non_empty_rows) > 0:
                # Add table metadata
                table_info = f"> 表格来源: PRTS Wiki | 行数: {len(rows)}"
                table_text.insert(1, table_info)
                table_text.append("")  # Add blank line after table

                # Check for duplicates before adding
                table_content_str = '\n'.join(table_text)
                table_hash = calculate_table_hash(table)

                # Only add if this is not a duplicate
                is_duplicate = False
                for processed_hash in processed_tables:
                    # Consider tables duplicate if they share more than 80% of their content
                    # Simple hash-based check first, then do more detailed comparison if needed
                    if table_hash == processed_hash[0]:
                        # Detailed comparison for same hash (rare but possible)
                        similarity = len(set(table_content_str.split()) & set(processed_hash[1].split())) / max(len(table_content_str.split()), len(processed_hash[1].split()))
                        if similarity > 0.8:
                            is_duplicate = True
                            logger.debug(f"Skipping duplicate table: {table_title[:50]}")
                            break

                if not is_duplicate:
                    table_contents.append(table_content_str)
                    processed_tables.append((table_hash, table_content_str))
                    logger.debug(f"Added table: {table_title[:50]} ({len(table_content_str)} chars)")
                else:
                    logger.debug(f"Skipped duplicate table: {table_title[:50]}")
        
        if table_contents:
            # **NEW**: Validate table content quality before merging
            valid_tables = []
            for idx, table_content in enumerate(table_contents):
                # Check if table has actual data rows (not just separators)
                data_rows = [line for line in table_content.split('\n')
                            if '|' in line and not line.startswith('>') and '---' not in line]

                if len(data_rows) >= 2:  # At least header + one data row
                    valid_tables.append(table_content)
                else:
                    # Add detailed logging for low-quality tables
                    table_header = table_content.split('\n')[0] if table_content else "Unknown"
                    logger.warning(f"Low-quality table detected (only {len(data_rows)} data rows): {table_header[:50]}...")
                    logger.debug(f"Full table content: {table_content[:200]}...")

                    # Optionally keep tables with at least some content
                    if len(data_rows) > 0 and len(table_content) > 50:
                        logger.info(f"Keeping marginal quality table: {table_header[:50]}")
                        valid_tables.append(table_content)

            if not valid_tables:
                logger.warning("No valid tables found with sufficient data rows")
                return ""

            # Merge similar skill tables to reduce redundancy
            merged_contents = self._merge_similar_tables(valid_tables)

            # Add introduction section
            introduction = "# 表格数据\n\n以下是从页面提取的结构化表格数据，按重要性排序：\n\n"
            combined = introduction + '\n\n---\n\n'.join(merged_contents)  # Separate tables with divider
            logger.info(f"Optimized table extraction result: {len(combined)} chars, {len(merged_contents)} tables (after merging)")
            # Apply text cleaning to format【tags】
            return self._clean_text(combined)

        return ""

    def _merge_similar_tables(self, table_contents: list) -> list:
        """Merge tables with similar skill names to reduce redundancy."""
        if not table_contents:
            return []

        merged_tables = []
        processed_indices = set()

        for i, table in enumerate(table_contents):
            if i in processed_indices:
                continue

            # Extract table title and content
            lines = table.split('\n')
            title = lines[0] if lines else ""

            # Look for other tables with similar titles (skill tables)
            similar_tables = [table]
            similar_indices = {i}

            for j, other_table in enumerate(table_contents):
                if j != i and j not in processed_indices:
                    other_lines = other_table.split('\n')
                    other_title = other_lines[0] if other_lines else ""

                    # Check if titles are similar (same skill name, different levels)
                    # Extract skill name from title
                    import re
                    skill_name_match = re.search(r'技能\s*-\s*表格\s*\d+|([^|]+)\s*-\s*表格', title)
                    other_skill_match = re.search(r'技能\s*-\s*表格\s*\d+|([^|]+)\s*-\s*表格', other_title)

                    if skill_name_match and other_skill_match:
                        skill1 = skill_name_match.group(1).strip()
                        skill2 = other_skill_match.group(1).strip()

                        # If skill names are similar (case-insensitive)
                        if (skill1.lower() == skill2.lower() or
                            skill1 in skill2 or skill2 in skill1):
                            similar_tables.append(other_table)
                            similar_indices.add(j)

            # If we found similar tables, try to merge them
            if len(similar_tables) > 1:
                # Extract skill name for merged table
                skill_name = re.search(r'技能\s*-\s*表格\s*\d+|([^|]+)\s*-\s*表格', title)
                if skill_name:
                    skill_name = skill_name.group(1).strip()
                    # Clean up skill name - remove extra # symbols and invalid characters
                    skill_name = re.sub(r'^#+\s*', '', skill_name)  # Remove leading #
                    skill_name = re.sub(r'[限兑\d]*$', '', skill_name)  # Remove trailing 限/兑/digits

                    # Create merged table
                    merged_table = f"## 技能 - {skill_name}\n\n"
                    merged_table += "> 表格来源: PRTS Wiki | 已合并多个表格\n\n"

                    # Combine all rows from similar tables
                    all_rows = []
                    headers_added = False

                    for t in similar_tables:
                        t_lines = t.split('\n')
                        for line in t_lines:
                            # Skip title and metadata lines
                            if line.startswith('##') or line.startswith('>') or not line.strip():
                                continue

                            # Add header if we see it
                            if not headers_added and '|' in line and not line.startswith('|'):
                                all_rows.append(line)
                                headers_added = True
                            elif line.startswith('|') or (line.count('|') > 0 and '---' in line):
                                # This is a table row or separator, skip duplicates
                                if line not in all_rows:
                                    all_rows.append(line)

                    if all_rows:
                        merged_table += '\n'.join(all_rows)
                        merged_table += '\n'
                        merged_tables.append(merged_table)

                        # Mark these indices as processed
                        processed_indices.update(similar_indices)
                        logger.debug(f"Merged {len(similar_tables)} tables for skill: {skill_name[:30]}")
            else:
                # No similar tables, keep as is
                if i not in processed_indices:
                    merged_tables.append(table)
                    processed_indices.add(i)

        return merged_tables
    
    def _extract_from_headings(self, soup: BeautifulSoup) -> str:
        """Extract content structured around headings."""
        logger.info("Trying heading-based extraction...")
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if not headings:
            return ""
        
        content_sections = []
        
        for heading in headings:
            # Get heading text
            heading_text = heading.get_text(strip=True)
            if not heading_text or len(heading_text) < 2:
                continue
            
            # Determine heading level (capped at 3 for Markdown)
            level = min(int(heading.name[1]), 3)
            content_sections.append(f"{'#' * level} {heading_text}")
            
            # Collect all content until next heading
            section_content = []
            sibling = heading.find_next_sibling()
            
            while sibling and sibling.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                # Skip navigation-like siblings
                skip = False
                for class_name in ['nav', 'menu', 'sidebar', 'footer']:
                    if class_name in sibling.get('class', []) or class_name in str(sibling.get('id', '')):
                        skip = True
                        break
                
                if not skip:
                    text = sibling.get_text(strip=True)
                    if text and len(text) > 10:  # Skip very short content
                        section_content.append(text)
                
                sibling = sibling.find_next_sibling()
            
            # Add section content if we found any
            if section_content:
                content_sections.append('\n\n'.join(section_content))
        
        if content_sections:
            combined = '\n\n'.join(content_sections)
            logger.info(f"Heading extraction result: {len(combined)} chars")
            # Apply text cleaning to format【tags】
            return self._clean_text(combined)

        return ""
    
    def _clean_text(self, text: str) -> str:
        """Enhanced text cleaning with more permissive content retention."""
        if not text:
            return ""
        
        # First, normalize line breaks and spaces
        text = re.sub(r'\r\n', '\n', text)  # Normalize Windows line breaks
        text = re.sub(r'[ \t]+', ' ', text)  # Normalize spaces and tabs
        
        # Split into lines for processing
        lines = text.split('\n')
        processed_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip completely empty lines initially
            if not line:
                continue
            
            # Enhanced navigation filtering - skip clearly useless content
            if (
                # Skip very short single-character navigation elements
                line in ['目', '录', '编辑'] or
                # Skip lines with excessive navigation keywords (PRTS Wiki specific)
                (
                    # Count navigation-related keywords
                    line.count('干员一览') >= 1 or  # "干员一览" appears
                    line.count('异格一览') >= 1 or  # "异格一览" appears
                    line.count('限') >= 2 or  # "限" appears multiple times (限兑限兑)
                    line.count('兑') >= 2 or  # "兑" appears multiple times
                    line.count('模组') >= 2 or  # "模组" appears multiple times
                    # Skip lines that are mostly navigation terms
                    (len(line) < 100 and
                     sum(1 for keyword in ['干员一览', '异格一览', '限', '兑', '模组', '天赋', '技能']
                         if keyword in line) >= 3)
                ) or
                # Skip known wiki administrative pages
                line.startswith('Category:') or
                line.startswith('File:') or
                line.startswith('Template:') or
                line.startswith('Special:') or
                # Skip pure punctuation
                re.match(r'^[.,;:/\\\-_+=*\[\]{}()<>|!@#$%^&*]+$', line)
            ):
                continue
            
            # Retain more potential content
            # Allow section numbers and short descriptive lines
            processed_lines.append(line)
            
            # Debug: Log when we keep content that was previously filtered
            if len(line) <= 5:
                logger.debug(f"Retaining short line: '{line}'")
        
        # Now intelligently join lines with more permissive merging rules
        final_lines = []
        i = 0
        
        while i < len(processed_lines):
            current_line = processed_lines[i]
            
            # Check if current line should be merged with next line
            if (i + 1 < len(processed_lines) and 
                not self._is_heading_line(current_line) and
                not self._is_list_item(current_line)):
                
                next_line = processed_lines[i + 1]
                
                # More permissive merging rules
                # Don't merge headings or list items
                if (not self._is_heading_line(next_line) and
                    not self._is_list_item(next_line)):
                    
                    # Be more flexible with line length
                    if len(current_line) < 150:  # Increased from 100
                        
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
        
        # Join with appropriate spacing with better paragraph handling
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
                
                # More balanced paragraph breaks
                # Add paragraph break for long content lines or between different content types
                if (len(line) > 40 and  # Slightly reduced from 50
                    i < len(final_lines) - 1 and 
                    # Don't add breaks between short lines that might be related
                    not (len(line) < 20 and len(final_lines[i+1]) < 20)):
                    result_parts.append('\n\n')
                else:
                    result_parts.append('\n')
        
        result = ''.join(result_parts)
        
        # Final cleanup - less aggressive
        # Reduce multiple newlines but allow more flexibility
        result = re.sub(r'\n{4,}', '\n\n\n', result)  # Allow up to 3 consecutive newlines
        
        # Only clean extreme cases of repeated punctuation
        result = re.sub(r'[。，、；：！？]{5,}', '...', result)  # Only clean 5+ repeated punctuation marks

        # Fix duplicate headings (e.g., "## ## Title" -> "## Title")
        result = re.sub(r'^#{3,}\s+', '', result, flags=re.MULTILINE)  # Remove excess # symbols
        result = re.sub(r'^##\s*##\s+(.+)$', r'## \1', result, flags=re.MULTILINE)  # Fix "## ## Title"

        # Clean up titles with invalid characters (e.g., "限 兑 兑 限 兑 兑 1")
        result = re.sub(r'^##\s+([限兑\d]+)$', r'', result, flags=re.MULTILINE)  # Remove invalid titles

        # Add line breaks before【character】tags for better readability
        result = re.sub(r'([^【\n])【', r'\1\n【', result)

        # Add line breaks before section headers (like "综合体检测试", "临床诊断分析")
        result = re.sub(r'([^。【\n])(综合体检测试|临床诊断分析|档案资料|客观履历|主观评价|晋升记录)', r'\1\n\n\2', result)
        # Also handle headers that come after punctuation
        result = re.sub(r'[。]\s*(综合体检测试|临床诊断分析|档案资料|客观履历|主观评价|晋升记录)', r'。\n\n\1', result)
        # Handle headers that are followed by content without punctuation
        result = re.sub(r'(综合体检测试|临床诊断分析|档案资料|客观履历|主观评价|晋升记录)\s+([^\n]+)\s+([提升造影])', r'\1\n\n\2 \3', result)

        # Add line breaks after【tags】before paragraph text (to separate content from descriptions)
        # Pattern: 【标签】标准恩希... -> 【标签】标准\n\n恩希...
        # Also handle cases like "【标签】标准\n\n综合体检测试"
        result = re.sub(r'(】[标准优良卓越]*(?:标准)?)\s*(恩希|造影|提升|保密等级|提升信赖)', r'\1\n\n\2', result)

        # Add line breaks between【tags】and following section headers
        result = re.sub(r'(【[^】]+】[^。！？；\n]*[。！？；])\s*(综合体检测试|临床诊断分析|档案资料|客观履历|主观评价|晋升记录)', r'\1\n\n\2', result)

        # Split long paragraphs for better readability
        def split_long_paragraphs(text, max_length=120):
            """Split long paragraphs into shorter ones at sentence boundaries."""
            lines = text.split('\n')
            result_lines = []

            for line in lines:
                # Skip headers, empty lines, and already short lines
                if not line.strip() or line.startswith('#') or len(line) <= max_length:
                    result_lines.append(line)
                    continue

                # Split long paragraph into sentences
                import re
                # Split at sentence-ending punctuation followed by a capital letter or newline
                sentences = re.split(r'([。！？；])(?=\S)', line)
                current_paragraph = ""

                for i in range(0, len(sentences), 2):
                    sentence = sentences[i]
                    punctuation = sentences[i+1] if i+1 < len(sentences) else ''
                    full_sentence = sentence + punctuation

                    # If adding this sentence would exceed max length, start new paragraph
                    if len(current_paragraph) + len(full_sentence) > max_length and current_paragraph:
                        result_lines.append(current_paragraph.strip())
                        current_paragraph = full_sentence
                    else:
                        current_paragraph += full_sentence

                # Add the last paragraph if not empty
                if current_paragraph.strip():
                    result_lines.append(current_paragraph.strip())

            return '\n'.join(result_lines)

        result = split_long_paragraphs(result)

        # Validate content quality and log warnings
        validation_warnings = []

        # Check for proper table structure
        if result.count('|') > 0:
            # Count table rows
            table_rows = [line for line in result.split('\n') if '|' in line and not line.startswith('#')]
            if table_rows:
                # Check if tables have consistent column counts
                for i, row in enumerate(table_rows[:10]):  # Check first 10 table rows
                    cols = row.split('|')
                    if len(cols) < 2:
                        validation_warnings.append(f"Table row {i} has fewer than 2 columns")
                logger.debug(f"Found {len(table_rows)} table rows, {len(validation_warnings)} warnings")

        # Check for excessive repeated content
        if '恩希欧迪斯' in result:
            # Count occurrences of long text blocks
            blocks = result.split('\n\n')
            long_blocks = [b for b in blocks if len(b) > 500]
            if len(long_blocks) > 3:
                validation_warnings.append(f"Found {len(long_blocks)} very long text blocks (>500 chars)")

        # Log validation results
        if validation_warnings:
            logger.info(f"Content validation: {len(validation_warnings)} warnings detected")
            for warning in validation_warnings[:5]:  # Log first 5 warnings
                logger.debug(f"  - {warning}")
        else:
            logger.debug("Content validation: No issues detected")

        # Ensure at least some content is preserved
        if not result.strip():
            logger.warning("Cleaned text resulted in empty content")
            # If all cleaning resulted in empty content, return a minimally processed version
            minimal_result = '\n'.join([line for line in lines if line.strip()])
            return minimal_result.strip() or "[Content extraction produced empty result]"

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
        """Check if line looks like a list item (excluding table rows)."""
        # Exclude table rows (they contain '|' which is markdown table syntax)
        if '|' in line and ('---' in line or line.count('|') >= 2):
            return False

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

            # Extract attack range from SVG
            attack_range_data = self._extract_attack_range(soup)
            if attack_range_data:
                metadata['attack_range'] = attack_range_data
                logger.debug(f"Extracted attack range data for {metadata['character_name']}")
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

    def _extract_attack_range(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """
        Extract attack range information from SVG images in the page.

        Args:
            soup: BeautifulSoup对象

        Returns:
            攻击范围数据字典或None，包含可视化文本
        """
        try:
            # 查找攻击范围SVG元素（通常在infobox或attack-range容器中）
            svg_selectors = [
                '.infobox svg',
                '.charbox svg',
                '.attack-range svg',
                'img[alt*="攻击范围"] + svg',
                'img[alt*="攻击范围"]',  # 有时SVG是内联的
                '.sp-skill svg',  # 技能范围也可能用SVG表示
            ]

            svg_element = None
            for selector in svg_selectors:
                svg_element = soup.select_one(selector)
                if svg_element:
                    logger.debug(f"Found attack range SVG with selector: {selector}")
                    break

            if not svg_element:
                logger.debug("No attack range SVG found on page")
                return None

            # 提取SVG内容
            svg_content = str(svg_element)

            # 解析攻击范围
            parser = AttackRangeParser()
            attack_range_data = parser.parse_svg(svg_content)

            if attack_range_data:
                logger.info(f"Successfully extracted attack range: {attack_range_data['pattern_name']}")

                # 添加可视化文本
                grid = attack_range_data.get('grid', [])
                if grid:
                    # 生成Border风格可视化
                    border_viz = self._visualize_attack_range_border(grid)
                    attack_range_data['border_visual'] = border_viz

                    # 生成Compact风格可视化
                    compact_viz = self._visualize_attack_range_compact(grid)
                    attack_range_data['compact_visual'] = compact_viz

                    # 生成向量数据库导出格式
                    db_export = self._export_attack_range_for_database(attack_range_data)
                    attack_range_data['database_export'] = db_export

                return attack_range_data
            else:
                logger.debug("Failed to parse attack range SVG")
                return None

        except Exception as e:
            logger.warning(f"Error extracting attack range: {e}")
            return None

    def _visualize_attack_range_border(self, grid: List[List[bool]]) -> str:
        """生成Border风格的攻击范围可视化"""
        if not grid or not grid[0]:
            return "无攻击范围"

        lines = []
        width = len(grid[0])

        # 顶部边框
        lines.append('┌' + '─' * width + '┐')

        # 中间内容
        for row in grid:
            line = '│'
            for cell in row:
                line += '█' if cell else ' '
            line += '│'
            lines.append(line)

        # 底部边框
        lines.append('└' + '─' * width + '┘')

        return '\n'.join(lines)

    def _visualize_attack_range_compact(self, grid: List[List[bool]]) -> str:
        """生成Compact风格的攻击范围可视化"""
        if not grid or not grid[0]:
            return "无攻击范围"

        lines = []
        for row in grid:
            line = ''.join('X' if cell else '.' for cell in row)
            lines.append(line)

        return '\n'.join(lines)

    def _export_attack_range_for_database(self, attack_range_data: Dict[str, Any]) -> Dict[str, Any]:
        """导出适合向量数据库的攻击范围格式"""
        grid = attack_range_data.get('grid', [])

        # 计算坐标列表
        coords = []
        for y, row in enumerate(grid):
            for x, cell in enumerate(row):
                if cell:
                    coords.append((x, y))

        # 生成Border可视化
        border_visual = attack_range_data.get('border_visual', '')
        compact_visual = attack_range_data.get('compact_visual', '')

        # 添加元数据
        metadata = {
            'type': attack_range_data.get('pattern_name', 'unknown'),
            'description': attack_range_data.get('description', ''),
            'range_type': attack_range_data.get('range_type', 'unknown'),
            'attack_count': attack_range_data.get('attack_cells', 0),
            'width': len(grid[0]) if grid else 0,
            'height': len(grid) if grid else 0,
            'coords': str(sorted(coords))
        }

        result = {
            'border': border_visual,
            'compact': compact_visual,
            'metadata': metadata
        }

        return result

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
    
    async def scrape_character_overview(self, overview_url: str, max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
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
    
    async def _extract_all_character_links_with_pagination(self, start_url: str, max_pages: Optional[int] = None) -> List[str]:
        """
        Extract character links from all pages using interactive pagination.

        Args:
            start_url: Starting overview page URL
            max_pages: Maximum number of pagination pages to process (uses config default if None)

        Returns:
            List of all character links across all pages
        """
        all_character_links = []
        max_pagination_pages = max_pages if max_pages is not None else MAX_PAGINATION_PAGES  # Use provided max_pages or config default
        
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
                logger.info(f"Processing pagination page {current_page}...")

                try:
                    # Get page content
                    content = await page.content()
                    soup = BeautifulSoup(content, 'html.parser')

                    # Extract character links from current page
                    page_links = self._extract_links_from_soup(soup, start_url)

                    if page_links:
                        all_character_links.extend(page_links)
                        logger.info(f"Page {current_page}: +{len(page_links)} links")

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
                        logger.info("No more pagination pages")
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
    
