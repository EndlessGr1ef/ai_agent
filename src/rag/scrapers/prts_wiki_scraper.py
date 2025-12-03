"""PRTS Wiki scraper for character information and related content."""

import asyncio
import logging
import re
import time
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
                 output_dir: str = None,
                 **kwargs):
        """
        Initialize PRTS Wiki scraper.

        Args:
            use_js_renderer: Whether to use JavaScript rendering for dynamic content
            content_selectors: CSS selectors for different content types
            output_dir: Output directory for scraped content
            **kwargs: Additional arguments for BaseScraper
        """
        # Extract output_dir before passing to parent
        self.output_dir = output_dir

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
        logger.info(f"===== START CONTENT EXTRACTION: {url} =====")
        extraction_start_time = time.time()
        try:
            if self.use_js_renderer:
                await self._ensure_js_renderer()
                logger.info(f"Rendering page with JS for content extraction: {url}")
                
                # Enhanced page rendering with custom waiting options
                page_data = await self.js_renderer.render_page(
                    url,
                    wait_for_function="() => document.readyState === 'complete'"
                )
                
                html_content = page_data['html']
                page_title = page_data['title']
                logger.info(f"Page rendered successfully, HTML length: {len(html_content)}, Title: {page_title}")
            else:
                response = self.make_request(url)
                html_content = response.text
                soup = BeautifulSoup(html_content, 'html.parser')
                page_title = soup.title.string if soup.title else ""
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Log page structure details
            logger.debug(f"Page title: {page_title}")
            logger.debug(f"HTML content length: {len(html_content)} chars")
            
            # Log key HTML elements for diagnostic purposes
            key_elements = ['div', 'section', 'main', 'article', 'table', 'h1', 'h2', 'h3', 'p']
            for elem in key_elements:
                count = len(soup.find_all(elem))
                if count > 0:
                    logger.debug(f"Found {count} {elem} elements")
            
            # Check for specific content patterns
            has_tables = len(soup.find_all('table')) > 0
            has_lists = len(soup.find_all(['ul', 'ol'])) > 0
            has_headings = len(soup.find_all(['h1', 'h2', 'h3'])) > 0
            logger.info(f"Content patterns detected - Tables: {has_tables}, Lists: {has_lists}, Headings: {has_headings}")
            
            # Extract main content
            logger.info("Attempting main content extraction with primary selectors...")
            main_content = self._extract_main_content(soup)
            main_content_str = str(main_content) if main_content else ""
            main_content_length = len(main_content_str)
            logger.info(f"Main content extraction result: {main_content_length} chars")
            
            # Log first 100 chars as sample if content exists
            if main_content_length > 0:
                sample = main_content_str[:100].replace('\n', ' ').replace('\r', '') + ("..." if main_content_length > 100 else "")
                logger.debug(f"Main content sample: {sample}")
            
            # Extract metadata
            metadata = self._extract_metadata(soup, url, page_title)
            
            # Determine content type
            content_type = self._determine_content_type(url, soup)
            logger.info(f"Detected content type: {content_type}")
            
            # Special handling for pages with tables (both table_data and character_page)
            if content_type in ['table_data', 'character_page'] and soup.find_all('table'):
                logger.info(f"Tables detected in {content_type}, prioritizing table extraction...")
                table_content = self._extract_from_tables(soup)
                if table_content and len(table_content.strip()) > 100 and '|' in table_content:  # Check for pipe chars in table content
                    logger.info(f"Successfully extracted table content: {len(table_content)} chars")
                    # Combine table content with a portion of regular content
                    regular_content = self._clean_content(main_content)
                    # Extract first 1000 chars of regular content as introduction
                    intro_content = regular_content[:1000].split('\n')[:10]  # Get first 10 lines or 1000 chars
                    intro_content = '\n'.join(intro_content)
                    # Combine intro and tables
                    cleaned_content = f"{intro_content}\n\n## 详细数据表格\n\n{table_content}"
                else:
                    logger.warning("Table extraction yielded limited results, falling back to standard extraction...")
                    cleaned_content = self._clean_content(main_content)
            else:
                # Standard content cleaning and structuring
                logger.info("Cleaning and structuring extracted content...")
                cleaned_content = self._clean_content(main_content)
            
            cleaned_content_length = len(cleaned_content)
            cleaned_content_lines = len(cleaned_content.strip().split('\n'))
            logger.info(f"Cleaned content stats: {cleaned_content_length} chars, {cleaned_content_lines} lines")
            
            # If cleaned content is empty or insufficient, try alternative extraction methods
            if not cleaned_content.strip() or (content_type == 'table_data' and '|' not in cleaned_content):
                logger.warning(f"Primary content extraction yielded insufficient content, trying fallback methods...")
                logger.info("Attempting fallback extraction strategies...")
                fallback_start_time = time.time()
                cleaned_content = self._extract_content_fallback(soup)
                fallback_time = time.time() - fallback_start_time
                fallback_length = len(cleaned_content)
                fallback_lines = len(cleaned_content.strip().split('\n'))
                logger.info(f"Fallback extraction completed in {fallback_time:.2f}s with {fallback_length} chars, {fallback_lines} lines")
            
            # Final content quality assessment
            final_content_length = len(cleaned_content)
            final_content_words = len(cleaned_content.split())
            content_quality = "EXCELLENT" if final_content_length > 1000 else "GOOD" if final_content_length > 500 else "MINIMAL" if final_content_length > 100 else "POOR"
            logger.info(f"Content extraction quality assessment: {content_quality} ({final_content_length} chars, ~{final_content_words} words)")
            
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
            
            logger.info(f"Content extraction COMPLETE for: {page_title} ({extraction_time:.2f}s)")
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
            
            logger.info(f"===== CONTENT EXTRACTION FAILED: {url} =====")
            raise ScrapingError(f"Failed to extract content: {e}")
        finally:
            logger.info(f"===== END CONTENT EXTRACTION: {url} =====")
    

    
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
            return cleaned
        
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
        if not tables:
            return ""
        
        table_contents = []
        
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
            # Skip tables that look like navigation or UI
            skip = False
            for class_name in ['nav', 'menu', 'sidebar', 'footer', 'pagination']:
                if class_name in table.get('class', []) or class_name in str(table.get('id', '')):
                    skip = True
                    break
            
            if skip:
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
            for row_idx, row in enumerate(rows):
                # Extract both th and td cells
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                # Skip empty rows
                if not any(cell_texts):
                    continue
                
                # Handle header row(s)
                if row.find_all('th') and (not first_data_row_processed or row_idx == 0):
                    # Add header row
                    table_text.append(" | ".join(cell_texts))
                    # Create proper separator row that matches the number of columns
                    separator = ["---"] * len(cell_texts)
                    table_text.append(" | ".join(separator))
                    has_header = True
                else:
                    # Regular data row
                    # More permissive filtering - allow shorter rows but skip truly trivial ones
                    if len(' '.join(cell_texts)) > 5:  # Skip only empty or single character rows
                        table_text.append(" | ".join(cell_texts))
                    first_data_row_processed = True
            
            # Only add tables with meaningful content
            # More permissive condition - allow tables with at least one data row
            non_empty_rows = [row for row in table_text if row.strip() and not row.startswith('#') and row != '---']
            if len(non_empty_rows) > 0:
                # Add table metadata
                table_info = f"> 表格来源: PRTS Wiki | 行数: {len(rows)}"
                table_text.insert(1, table_info)
                table_text.append("")  # Add blank line after table
                
                table_contents.append('\n'.join(table_text))
        
        if table_contents:
            # Add introduction section
            introduction = "# 表格数据\n\n以下是从页面提取的结构化表格数据，按重要性排序：\n\n"
            combined = introduction + '\n\n---\n\n'.join(table_contents)  # Separate tables with divider
            logger.info(f"Optimized table extraction result: {len(combined)} chars, {len(table_contents)} tables")
            return combined
        
        return ""
    
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
            return combined
        
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
            
            # More permissive filtering - only skip clearly useless content
            if (
                # Only skip very specific navigation elements
                line in ['目', '录', '编辑'] or  
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
    
    
    
    
    
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    
    
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
        """Determine if this page is a target page for this scraper."""
        # This is a generic implementation.
        # Subclasses should override this method with specific logic.
        return True

        return self._is_character_page(url, soup=None)
    
