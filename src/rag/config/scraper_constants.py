"""
Configuration constants for PRTS Wiki scraper.
"""

# Timeout values (in milliseconds)
DEFAULT_TIMEOUT = 30000
NETWORK_IDLE_TIMEOUT = 15000
SELECTOR_TIMEOUT = 10000
CONTENT_LOAD_TIMEOUT = 5000
PAGE_NAVIGATION_WAIT = 3000

# Pagination limits
MAX_PAGINATION_PAGES = 10
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_NUMBER = 20

# Content processing limits
MIN_CHARACTER_NAME_LENGTH = 2
MAX_LINE_LENGTH_FOR_MERGE = 100
MIN_CONTENT_LENGTH = 500
MAX_CONTENT_READ_LENGTH = 500

# CSS Selectors for PRTS Wiki
CSS_SELECTORS = {
    # Character identification
    'character_name': '.name',
    'character_links': 'a[href*="/w/"]',
    
    # Content areas
    'main_content': '#mw-content-text, .mw-parser-output',
    'content_text': '.mw-parser-output',
    'article_content': '#mw-content-text',
    
    # Pagination
    'pagination_container': '.paginations-container',
    'pagination_item': '.checkbox-container',
    'selected_page': '.checkbox-container.selected',
    
    # Character page indicators
    'character_indicators': [
        '.character-info',
        '.operator-info', 
        '#charart',
        '.char-info',
        'table.wikitable:contains("干员")',
        'table.wikitable:contains("稀有度")'
    ],
    
    # Link extraction patterns
    'link_selectors': [
        'a[href*="/w/"]',  # PRTS Wiki character pages
        'a[title*="干员"]',
        'a[title*="角色"]',
        '.character-link a',
        '.operator-link a',
        'table tr td a[href*="/w/"]'
    ]
}

# Character page URL patterns
CHARACTER_URL_PATTERNS = [
    '/w/',  # Basic wiki page pattern
    '干员',  # Character keyword in Chinese
    '角色',  # Character keyword in Chinese
]

# Character exclusion patterns
EXCLUDED_PATTERNS = [
    '干员一览',  # Character overview page
    '分类:',    # Category pages
    '模板:',    # Template pages
    'Category:', # English category pages
    'Template:', # English template pages
    '用户:',    # User pages
    'User:',    # English user pages
    '讨论:',    # Discussion pages
    'Talk:',    # English talk pages
    '帮助:',    # Help pages
    'Help:',    # English help pages
]

# File naming settings
FILENAME_MAX_LENGTH = 100
INVALID_FILENAME_CHARS = '<>:"/\\|?*'
FILENAME_REPLACEMENT_CHAR = '_'

# Retry settings
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF_FACTOR = 2.0

# Logging settings
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'