"""Base scraper abstract class providing common web scraping functionality."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import time
import random
from urllib.parse import urljoin, urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Suppress InsecureRequestWarning for unverified HTTPS requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Custom exception for scraping-related errors."""
    pass


class BaseScraper(ABC):
    """Abstract base class for web scrapers."""
    
    def __init__(self, 
                 delay_range: tuple = (1, 3),
                 max_retries: int = 3,
                 timeout: int = 30,
                 user_agent: str = None):
        """
        Initialize the base scraper.
        
        Args:
            delay_range: Tuple of (min, max) seconds to wait between requests
            max_retries: Maximum number of retry attempts
            timeout: Request timeout in seconds
            user_agent: Custom user agent string
        """
        self.delay_range = delay_range
        self.max_retries = max_retries
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        
        # Setup session with retry strategy
        self.session = requests.Session()
        self.session.verify = False  # Disable SSL verification due to environment issues
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set default headers
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
    
    def add_delay(self) -> None:
        """Add random delay between requests to be respectful."""
        delay = random.uniform(*self.delay_range)
        logger.debug(f"Adding delay of {delay:.2f} seconds")
        time.sleep(delay)
    
    def make_request(self, url: str, method: str = 'GET', **kwargs) -> requests.Response:
        """
        Make HTTP request with error handling and retries.
        
        Args:
            url: URL to request
            method: HTTP method (GET, HEAD, etc.)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
            
        Raises:
            ScrapingError: If request fails after all retries
        """
        try:
            logger.info(f"Making {method} request to: {url}")
            
            if method.upper() == 'HEAD':
                response = self.session.head(url, timeout=self.timeout, **kwargs)
            else:
                response = self.session.get(url, timeout=self.timeout, **kwargs)
                
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"{method} request failed for {url}: {e}")
            raise ScrapingError(f"Failed to fetch {url}: {e}")
    
    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and accessible."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def normalize_url(self, url: str, base_url: str = None) -> str:
        """Normalize and resolve relative URLs."""
        if base_url and not url.startswith(('http://', 'https://')):
            return urljoin(base_url, url)
        return url
    
    @abstractmethod
    def extract_content(self, url: str) -> Dict[str, Any]:
        """
        Extract content from a single URL.
        
        Args:
            url: URL to scrape
            
        Returns:
            Dictionary containing extracted content and metadata
        """
        pass
    
    @abstractmethod
    def extract_links(self, url: str) -> List[str]:
        """
        Extract relevant links from a page.
        
        Args:
            url: URL to extract links from
            
        Returns:
            List of URLs
        """
        pass
    
    @abstractmethod
    def is_target_page(self, url: str, content: str = None) -> bool:
        """
        Determine if a page matches the target criteria.
        
        Args:
            url: URL to check
            content: Optional page content for additional checks
            
        Returns:
            True if page matches target criteria
        """
        pass
    
    def scrape_multiple(self, urls: List[str]) -> List[Dict[str, Any]]:
        """
        Scrape multiple URLs with error handling and delays.
        
        Args:
            urls: List of URLs to scrape
            
        Returns:
            List of extracted content dictionaries
        """
        results = []
        total_urls = len(urls)
        
        for i, url in enumerate(urls, 1):
            try:
                logger.info(f"Scraping {i}/{total_urls}: {url}")
                content = self.extract_content(url)
                results.append(content)
                
                # Add delay between requests (except for the last one)
                if i < total_urls:
                    self.add_delay()
                    
            except ScrapingError as e:
                logger.error(f"Failed to scrape {url}: {e}")
                # Continue with next URL instead of failing completely
                continue
            except Exception as e:
                logger.error(f"Unexpected error scraping {url}: {e}")
                continue
        
        logger.info(f"Successfully scraped {len(results)}/{total_urls} URLs")
        return results
    
    def __del__(self):
        """Cleanup resources."""
        if hasattr(self, 'session'):
            self.session.close()