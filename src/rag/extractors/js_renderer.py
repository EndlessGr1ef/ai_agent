"""JavaScript renderer using Playwright for handling dynamic content."""

import asyncio
import logging
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger(__name__)


class JSRenderError(Exception):
    """Custom exception for JavaScript rendering errors."""
    pass


class JSRenderer:
    """Handles JavaScript rendering using Playwright."""
    
    def __init__(self, 
                 headless: bool = True,
                 timeout: int = 30000,
                 wait_for_selector: str = None,
                 wait_for_network_idle: bool = True,
                 viewport_size: Dict[str, int] = None):
        """
        Initialize the JavaScript renderer.
        
        Args:
            headless: Run browser in headless mode
            timeout: Page load timeout in milliseconds
            wait_for_selector: CSS selector to wait for before considering page loaded
            wait_for_network_idle: Wait for network to be idle
            viewport_size: Browser viewport size {'width': 1280, 'height': 720}
        """
        self.headless = headless
        self.timeout = timeout
        self.wait_for_selector = wait_for_selector
        self.wait_for_network_idle = wait_for_network_idle
        self.viewport_size = viewport_size or {'width': 1280, 'height': 720}
        
        self._playwright = None
        self._browser = None
        self._context = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def start(self) -> None:
        """Start Playwright and browser."""
        try:
            self._playwright = await async_playwright().start()
            
            # Launch browser with optimized settings
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            # Create context with user agent and viewport
            self._context = await self._browser.new_context(
                viewport=self.viewport_size,
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            
            logger.info("Playwright browser started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Playwright: {e}")
            raise JSRenderError(f"Failed to initialize browser: {e}")
    
    async def close(self) -> None:
        """Close browser and Playwright."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Playwright browser closed")
        except Exception as e:
            logger.error(f"Error closing Playwright: {e}")
    
    async def render_page(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Render a page and return HTML content with metadata.
        
        Args:
            url: URL to render
            **kwargs: Additional options for page rendering
            
        Returns:
            Dictionary containing rendered content and metadata
        """
        if not self._context:
            raise JSRenderError("Browser not started. Use async context manager or call start()")
        
        page = None
        try:
            page = await self._context.new_page()
            
            # Set page timeout
            page.set_default_timeout(self.timeout)
            
            logger.info(f"Rendering page: {url}")
            
            # Navigate to page
            response = await page.goto(url, wait_until='domcontentloaded')
            
            if not response or response.status >= 400:
                raise JSRenderError(f"Failed to load page: HTTP {response.status if response else 'No response'}")
            
            # Wait for network idle if requested
            if self.wait_for_network_idle:
                try:
                    await page.wait_for_load_state('networkidle', timeout=15000)
                    logger.info("Network idle state reached")
                except PlaywrightTimeoutError:
                    logger.warning("Network idle timeout - continuing anyway")
            
            # Wait for specific selector if provided
            if self.wait_for_selector:
                try:
                    await page.wait_for_selector(self.wait_for_selector, timeout=15000)
                    logger.info(f"Successfully waited for selector: {self.wait_for_selector}")
                except PlaywrightTimeoutError:
                    logger.warning(f"Timeout waiting for selector: {self.wait_for_selector}")
            
            # For PRTS wiki character list pages, wait for dynamic content
            if '干员一览' in url or 'character' in url.lower():
                logger.info("Character overview page detected, waiting for dynamic content...")
                
                # Try to wait for character list elements to appear
                character_list_selectors = [
                    '.name',  # Character name elements
                    '.operator-card',  # Operator cards
                    '.character-card',  # Character cards
                    '.smw-columnlist-container',  # SMW column list
                    'a[href*="/w/"]'  # Any wiki links
                ]
                
                for selector in character_list_selectors:
                    try:
                        await page.wait_for_selector(selector, timeout=5000)
                        logger.info(f"✓ Character list elements found: {selector}")
                        
                        # Additional wait for content to fully load
                        await page.wait_for_timeout(2000)
                        break
                    except PlaywrightTimeoutError:
                        logger.debug(f"Selector not found: {selector}")
                        continue
                else:
                    logger.warning("No character list selectors found, content may not be loaded")
                    # Still wait a bit for any remaining JS
                    await page.wait_for_timeout(3000)
            
            # Additional custom wait conditions
            custom_wait = kwargs.get('wait_for_function')
            if custom_wait:
                await page.wait_for_function(custom_wait)
            
            # Get page content and metadata
            content = await page.content()
            title = await page.title()
            final_url = page.url
            
            # Get page dimensions
            viewport = page.viewport_size
            
            result = {
                'html': content,
                'title': title,
                'url': final_url,
                'original_url': url,
                'viewport': viewport,
                'status_code': response.status if response else None,
                'headers': dict(response.headers) if response else None,
            }
            
            logger.info(f"Successfully rendered page: {title}")
            return result
            
        except PlaywrightTimeoutError as e:
            logger.error(f"Timeout rendering {url}: {e}")
            raise JSRenderError(f"Timeout rendering page: {e}")
        except Exception as e:
            logger.error(f"Error rendering {url}: {e}")
            raise JSRenderError(f"Failed to render page: {e}")
        finally:
            if page:
                await page.close()
    
    async def extract_links(self, url: str, selector: str = "a[href]") -> List[str]:
        """
        Extract links from a rendered page.
        
        Args:
            url: URL to extract links from
            selector: CSS selector to find links
            
        Returns:
            List of extracted URLs
        """
        page_data = await self.render_page(url)
        page = None
        
        try:
            page = await self._context.new_page()
            await page.set_content(page_data['html'])
            
            # Extract href attributes
            links = await page.evaluate(f"""
                Array.from(document.querySelectorAll('{selector}')).map(link => link.href)
            """)
            
            # Filter and normalize links
            base_url = page_data['url']
            normalized_links = []
            
            for link in links:
                if link and link.startswith(('http://', 'https://')):
                    normalized_links.append(link)
                elif link and link.startswith('/'):
                    from urllib.parse import urljoin
                    normalized_links.append(urljoin(base_url, link))
            
            return list(set(normalized_links))  # Remove duplicates
            
        except Exception as e:
            logger.error(f"Error extracting links from {url}: {e}")
            raise JSRenderError(f"Failed to extract links: {e}")
        finally:
            if page:
                await page.close()
    
    async def wait_for_content(self, page: Page, 
                              content_selector: str,
                              timeout: int = 10000) -> bool:
        """
        Wait for specific content to appear on the page.
        
        Args:
            page: Playwright page object
            content_selector: CSS selector to wait for
            timeout: Timeout in milliseconds
            
        Returns:
            True if content appeared, False if timeout
        """
        try:
            await page.wait_for_selector(content_selector, timeout=timeout)
            return True
        except PlaywrightTimeoutError:
            return False
    
    async def scroll_and_wait(self, page: Page, 
                             scroll_pause: float = 2.0,
                             max_scrolls: int = 5) -> None:
        """
        Scroll page to trigger lazy loading content.
        
        Args:
            page: Playwright page object
            scroll_pause: Seconds to wait between scrolls
            max_scrolls: Maximum number of scroll attempts
        """
        for i in range(max_scrolls):
            # Scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(scroll_pause)
            
            # Check if new content loaded
            current_height = await page.evaluate("document.body.scrollHeight")
            await asyncio.sleep(0.5)
            new_height = await page.evaluate("document.body.scrollHeight")
            
            if current_height == new_height:
                break  # No new content loaded