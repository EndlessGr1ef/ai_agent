"""Configuration settings for web scrapers."""

import os
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ScraperConfig:
    """Configuration for web scrapers."""
    
    # Browser settings
    headless: bool = True
    timeout: int = 30000  # milliseconds
    viewport_width: int = 1280
    viewport_height: int = 720
    
    # Request settings
    delay_range: tuple = (1, 3)  # seconds between requests
    max_retries: int = 3
    request_timeout: int = 30  # seconds
    
    # Content processing
    use_js_renderer: bool = True
    wait_for_network_idle: bool = True
    content_selectors: Dict[str, str] = field(default_factory=lambda: {
        'main_content': '#mw-content-text, .mw-parser-output',
        'character_links': 'a[href*="/w/"], a[title]',
        'character_info': '.character-info, .infobox, .character-detail',
    })
    
    # Output settings
    output_dir: str = "scraped_content"
    save_markdown: bool = True
    include_metadata: bool = True
    
    # ChromaDB settings
    chroma_host: str = "localhost"
    chroma_port: int = 9000
    collection_name: str = "scraped_content"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Text processing
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    @classmethod
    def from_env(cls) -> 'ScraperConfig':
        """Create config from environment variables."""
        return cls(
            headless=os.getenv('SCRAPER_HEADLESS', 'true').lower() == 'true',
            timeout=int(os.getenv('SCRAPER_TIMEOUT', '30000')),
            use_js_renderer=os.getenv('SCRAPER_USE_JS', 'true').lower() == 'true',
            output_dir=os.getenv('SCRAPER_OUTPUT_DIR', 'scraped_content'),
            chroma_host=os.getenv('CHROMA_HOST', 'localhost'),
            chroma_port=int(os.getenv('CHROMA_PORT', '9000')),
            collection_name=os.getenv('CHROMA_COLLECTION', 'scraped_content'),
            embedding_model=os.getenv('EMBED_MODEL_NAME', 'BAAI/bge-large-zh-v1.5'),
            chunk_size=int(os.getenv('CHUNK_SIZE', '1000')),
            chunk_overlap=int(os.getenv('CHUNK_OVERLAP', '200')),
        )


@dataclass
class PRTSWikiConfig(ScraperConfig):
    """Configuration specifically for PRTS Wiki scraping."""
    
    # PRTS-specific settings
    base_url: str = "https://prts.wiki"
    character_overview_url: str = "https://prts.wiki/w/%E5%B9%B2%E5%91%98%E4%B8%80%E8%A7%88"
    
    # Content selectors specific to PRTS wiki
    content_selectors: Dict[str, str] = field(default_factory=lambda: {
        'character_list': '.smw-columnlist-container, .character-list, .wikitable',
        'character_info': '.character-info, .infobox, .character-detail',
        'main_content': '#mw-content-text, .mw-parser-output',
        'character_links': 'a[href*="/w/"], a[title]',
        'navigation': '.navbox, .navigation-box',
        'sidebar': '#mw-panel, .sidebar',
    })
    
    # PRTS-specific processing
    collection_name: str = "prts_wiki"
    max_pages: Optional[int] = None
    
    # Character page filtering
    character_url_patterns: list = field(default_factory=lambda: [
        r'/w/[^/]+$',  # Single character pages
        r'/w/.+(?<!一览)$'  # Exclude overview pages
    ])
    
    @classmethod
    def for_prts_wiki(cls) -> 'PRTSWikiConfig':
        """Create optimized config for PRTS Wiki."""
        base_config = ScraperConfig.from_env()
        return cls(
            **base_config.__dict__,
            collection_name="prts_wiki",
            wait_for_network_idle=True,  # Important for wiki pages
            delay_range=(2, 4),  # Be more respectful to wiki
        )


def get_scraper_config(scraper_type: str = "default") -> ScraperConfig:
    """Get scraper configuration by type."""
    if scraper_type.lower() == "prts" or scraper_type.lower() == "prts_wiki":
        return PRTSWikiConfig.for_prts_wiki()
    else:
        return ScraperConfig.from_env()
